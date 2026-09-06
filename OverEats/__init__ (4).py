import os
import json
import hashlib
import hmac as hmac_module
import secrets
import time
import logging
import socket
import struct
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, g, render_template
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from crypto.notes_crypto import encrypt_note, decrypt_note, export_note_blob, import_note_blob

app = Flask(__name__,
    template_folder='/app/templates',
    static_folder='/app/static')

DATABASE_URL     = os.environ.get('DATABASE_URL', 'postgresql://overeats:overeats_secret@postgres:5432/overeats')
INTERNAL_SECRET  = os.environ.get('INTERNAL_SECRET', 'SuperSecretInternalKey2026')
def _load_encryption_key() -> bytes:
    key_file = os.environ.get('ENCRYPTION_KEY_FILE', '/data/encryption_key')
    try:
        with open(key_file) as f:
            hexkey = f.read().strip()
        if len(hexkey) == 32:        
            return bytes.fromhex(hexkey)
    except FileNotFoundError:
        pass
    hexkey = secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
        with open(key_file, 'w') as f:
            f.write(hexkey)
    except OSError:
        pass
    return bytes.fromhex(hexkey)

ENCRYPTION_KEY   = _load_encryption_key()
LIVETRACK_HOST   = os.environ.get('LIVETRACK_HOST', 'livetrack')
LIVETRACK_PORT   = int(os.environ.get('LIVETRACK_PORT', '9090'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('overeats')



db_pool = ThreadedConnectionPool(
    minconn=1,
    maxconn=2,
    dsn=DATABASE_URL,
)

def get_db():
    if 'db' not in g:
        g.db = db_pool.getconn()
        g.db.autocommit = True
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        try:
            db_pool.putconn(db, close=bool(db.closed))
        except Exception:
            try:
                db.close()
            except Exception:
                pass

def db_query(sql, params=None, fetchone=False, fetchall=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    if fetchone:
        return cur.fetchone()
    if fetchall:
        return cur.fetchall()
    return None

def db_execute(sql, params=None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    return cur



def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(user_id):
    token = secrets.token_hex(32)
    expires = datetime.now() + timedelta(hours=1)
    db_execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires)
    )
    return token

def get_current_user():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    return db_query(
        """SELECT u.id, u.username, u.role FROM users u
           JOIN sessions s ON s.user_id = u.id
           WHERE s.token = %s AND s.expires_at > NOW()""",
        (token,), fetchone=True
    )

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def check_internal_auth():
    internal_auth = request.headers.get('X-Internal-Auth', '')
    return internal_auth == INTERNAL_SECRET



def run_cleanup():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT cleanup_old_data()")
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def cleanup_loop():
    while True:
        time.sleep(60)
        run_cleanup()

cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
cleanup_thread.start()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/howto')
def howto_page():
    return render_template('howto.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    role     = data.get('role', 'customer')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if role not in ('customer', 'restaurant', 'driver'):
        return jsonify({"error": "Role must be customer, restaurant, or driver"}), 400
    if len(username) > 64:
        return jsonify({"error": "Username too long"}), 400

    pw_hash = hash_password(password)
    token = secrets.token_hex(32)
    expires = datetime.now() + timedelta(hours=1)
    try:
        cur = db_execute(
            """WITH new_user AS (
                   INSERT INTO users (username, password_hash, role)
                   VALUES (%s, %s, %s)
                   RETURNING id
               )
               INSERT INTO sessions (token, user_id, expires_at)
               SELECT %s, id, %s FROM new_user
               RETURNING user_id""",
            (username, pw_hash, role, token, expires)
        )
        user_id = cur.fetchone()['user_id']
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Username already taken"}), 409

    return jsonify({"user_id": user_id, "token": token}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get('username', '')
    password = data.get('password', '')
    pw_hash  = hash_password(password)

    user = db_query(
        "SELECT id, username, role FROM users WHERE username = %s AND password_hash = %s",
        (username, pw_hash), fetchone=True
    )
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_session(user['id'])
    return jsonify({"user_id": user['id'], "token": token, "role": user['role']})



@app.route('/api/restaurants', methods=['POST'])
@require_auth
def create_restaurant():
    if g.current_user['role'] != 'restaurant':
        return jsonify({"error": "Only restaurant users can create restaurants"}), 403

    data        = request.get_json()
    name        = data.get('name', '').strip()
    cuisine     = data.get('cuisine', '').strip()
    description = data.get('description', '').strip()

    if not name:
        return jsonify({"error": "Restaurant name required"}), 400

    cur = db_execute(
        "INSERT INTO restaurants (user_id, name, cuisine, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (g.current_user['id'], name, cuisine, description)
    )
    return jsonify({"restaurant_id": cur.fetchone()['id']}), 201

@app.route('/api/restaurants', methods=['GET'])
def list_restaurants():
    restaurants = db_query(
        "SELECT id, name, cuisine, description FROM restaurants ORDER BY id DESC LIMIT 100",
        fetchall=True
    )
    return jsonify({"restaurants": restaurants or []})
    
@app.route('/api/restaurants/<int:rest_id>/menu', methods=['POST'])
@require_auth
def add_menu_item(rest_id):
    data = request.get_json()
    cur = db_execute(
        """INSERT INTO menu_items (restaurant_id, name, description, price)
           SELECT id, %s, %s, %s
           FROM restaurants
           WHERE id = %s AND user_id = %s
           RETURNING id""",
        (
            data.get('name'),
            data.get('description'),
            data.get('price'),
            rest_id,
            g.current_user['id']
        )
    )
    item = cur.fetchone()
    if not item:
        return jsonify({"error": "Restaurant not found or not yours"}), 404
    return jsonify({"item_id": item['id']}), 201

@app.route('/api/restaurants/<int:rest_id>/menu', methods=['GET'])
def get_menu(rest_id):
    items = db_query(
        "SELECT id, name, description, price, available FROM menu_items WHERE restaurant_id = %s",
        (rest_id,), fetchall=True
    )
    return jsonify({"menu": items or []})



@app.route('/api/orders', methods=['POST'])
@require_auth
def place_order():
    if g.current_user['role'] != 'customer':
        return jsonify({"error": "Only customers can place orders"}), 403

    data                 = request.get_json()
    restaurant_id        = data.get('restaurant_id')
    items                = data.get('items', [])
    special_instructions = data.get('special_instructions', '')

    rest = db_query("SELECT id FROM restaurants WHERE id = %s", (restaurant_id,), fetchone=True)
    if not rest:
        return jsonify({"error": "Restaurant not found"}), 404

    total = 0
    for item in items:
        mi = db_query(
            "SELECT price FROM menu_items WHERE id = %s AND restaurant_id = %s",
            (item.get('menu_item_id'), restaurant_id), fetchone=True
        )
        if mi:
            total += float(mi['price']) * item.get('quantity', 1)

    cur = db_execute(
        "INSERT INTO orders (customer_id, restaurant_id, items, special_instructions, total_price) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (g.current_user['id'], restaurant_id, json.dumps(items), special_instructions, total)
    )
    return jsonify({"order_id": cur.fetchone()['id']}), 201

@app.route('/api/orders', methods=['GET'])
@require_auth
def list_orders():
    user = g.current_user
    if user['role'] == 'customer':
        orders = db_query(
            "SELECT id, restaurant_id, items, special_instructions, status, total_price, created_at FROM orders WHERE customer_id = %s ORDER BY created_at DESC",
            (user['id'],), fetchall=True
        )
    elif user['role'] == 'restaurant':
        orders = db_query(
            """SELECT o.id, o.customer_id, o.items, o.special_instructions, o.status, o.total_price, o.created_at
               FROM orders o JOIN restaurants r ON o.restaurant_id = r.id
               WHERE r.user_id = %s ORDER BY o.created_at DESC""",
            (user['id'],), fetchall=True
        )
    elif user['role'] == 'driver':
        orders = db_query(
            """SELECT o.id, o.restaurant_id, o.items, o.status, o.total_price, o.created_at
               FROM orders o JOIN deliveries d ON d.order_id = o.id
               WHERE d.driver_id = %s ORDER BY o.created_at DESC""",
            (user['id'],), fetchall=True
        )
    else:
        orders = []

    for o in (orders or []):
        if o.get('created_at'):
            o['created_at'] = o['created_at'].isoformat()

    return jsonify({"orders": orders or []})

@app.route('/api/orders/recent', methods=['GET'])
def recent_orders():
    orders = db_query(
        """SELECT o.id, o.restaurant_id, r.name as restaurant_name, o.status, o.created_at
           FROM orders o JOIN restaurants r ON o.restaurant_id = r.id
           ORDER BY o.created_at DESC LIMIT 50""",
        fetchall=True
    )
    for o in (orders or []):
        if o.get('created_at'):
            o['created_at'] = o['created_at'].isoformat()
    return jsonify({"orders": orders or []})

@app.route('/api/orders/<int:order_id>/details', methods=['GET'])
def get_order_details(order_id):
    if check_internal_auth():
        order = db_query(
            "SELECT id, customer_id, restaurant_id, items, special_instructions, status, total_price, created_at FROM orders WHERE id = %s",
            (order_id,), fetchone=True
        )
        if not order:
            return jsonify({"error": "Order not found"}), 404
        if order.get('created_at'):
            order['created_at'] = order['created_at'].isoformat()
        return jsonify({"order": order})

    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    order = db_query("SELECT * FROM orders WHERE id = %s", (order_id,), fetchone=True)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    authorized = False

    if order['customer_id'] == user['id']:
        authorized = True

    if not authorized:
        rest = db_query(
            "SELECT id FROM restaurants WHERE id = %s AND user_id = %s",
            (order['restaurant_id'], user['id']), fetchone=True
        )
        if rest:
            authorized = True

    if not authorized:
        delivery = db_query(
            "SELECT id FROM deliveries WHERE order_id = %s AND driver_id = %s",
            (order_id, user['id']), fetchone=True
        )
        if delivery:
            authorized = True

    if not authorized:
        return jsonify({"error": "Access denied"}), 403

    if order.get('created_at'):
        order['created_at'] = order['created_at'].isoformat()
    return jsonify({"order": dict(order)})

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@require_auth
def update_order_status(order_id):
    data       = request.get_json()
    new_status = data.get('status')

    order = db_query("SELECT * FROM orders WHERE id = %s", (order_id,), fetchone=True)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    user       = g.current_user
    authorized = False

    if user['role'] == 'restaurant':
        rest = db_query(
            "SELECT id FROM restaurants WHERE id = %s AND user_id = %s",
            (order['restaurant_id'], user['id']), fetchone=True
        )
        if rest:
            authorized = True

    if user['role'] == 'driver':
        delivery = db_query(
            "SELECT id FROM deliveries WHERE order_id = %s AND driver_id = %s",
            (order_id, user['id']), fetchone=True
        )
        if delivery:
            authorized = True

    if not authorized:
        return jsonify({"error": "Not authorized"}), 403

    db_execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
    return jsonify({"status": "updated"})



@app.route('/api/deliveries', methods=['POST'])
@require_auth
def create_delivery():
    if check_internal_auth():
        data      = request.get_json()
        order_id  = data.get('order_id')
        driver_id = data.get('driver_id')

        order = db_query("SELECT id FROM orders WHERE id = %s", (order_id,), fetchone=True)
        if not order:
            return jsonify({"error": "Order not found"}), 404

        cur = db_execute(
            "INSERT INTO deliveries (order_id, driver_id) VALUES (%s, %s) RETURNING id",
            (order_id, driver_id)
        )
        return jsonify({"delivery_id": cur.fetchone()['id']}), 201

    user      = g.current_user
    data      = request.get_json()
    order_id  = data.get('order_id')
    driver_id = data.get('driver_id')

    order = db_query("SELECT id, restaurant_id FROM orders WHERE id = %s", (order_id,), fetchone=True)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    rest = db_query(
        "SELECT id FROM restaurants WHERE id = %s AND user_id = %s",
        (order['restaurant_id'], user['id']), fetchone=True
    )
    if not rest:
        return jsonify({"error": "Only the restaurant owner for this order can assign deliveries"}), 403

    cur = db_execute(
        "INSERT INTO deliveries (order_id, driver_id) VALUES (%s, %s) RETURNING id",
        (order_id, driver_id)
    )
    return jsonify({"delivery_id": cur.fetchone()['id']}), 201

@app.route('/api/deliveries/active', methods=['GET'])
@require_auth
def active_deliveries():
    if g.current_user['role'] != 'driver':
        return jsonify({"error": "Only drivers"}), 403

    deliveries = db_query(
        """SELECT d.id, d.order_id, d.status, o.restaurant_id
           FROM deliveries d JOIN orders o ON d.order_id = o.id
           WHERE d.driver_id = %s AND d.status != 'delivered'""",
        (g.current_user['id'],), fetchall=True
    )
    return jsonify({"deliveries": deliveries or []})


# ── Routes: Order Notes ───────────────────────────────────────────────────────

@app.route('/api/orders/<int:order_id>/notes', methods=['POST'])
@require_auth
def create_note(order_id):
    if g.current_user['role'] != 'customer':
        return jsonify({"error": "Only customers can create notes"}), 403

    order = db_query(
        "SELECT id FROM orders WHERE id = %s AND customer_id = %s",
        (order_id, g.current_user['id']), fetchone=True
    )
    if not order:
        return jsonify({"error": "Order not found or not yours"}), 404

    data      = request.get_json()
    note_text = data.get('note', '')
    if not note_text:
        return jsonify({"error": "Note content required"}), 400

    encrypted_data, hmac_sig = encrypt_note(
        owner_id=g.current_user['id'],
        note_text=note_text,
        key=ENCRYPTION_KEY
    )

    cur = db_execute(
        "INSERT INTO order_notes (order_id, customer_id, encrypted_data, hmac_signature) VALUES (%s, %s, %s, %s) RETURNING id",
        (order_id, g.current_user['id'],
         psycopg2.Binary(encrypted_data), psycopg2.Binary(hmac_sig))
    )
    return jsonify({"note_id": cur.fetchone()['id']}), 201

@app.route('/api/orders/<int:order_id>/notes', methods=['GET'])
@require_auth
def get_notes(order_id):
    notes = db_query(
        "SELECT id, encrypted_data, hmac_signature, created_at FROM order_notes WHERE order_id = %s",
        (order_id,), fetchall=True
    )

    result = []
    for note in (notes or []):
        try:
            decrypted = decrypt_note(
                encrypted_data=bytes(note['encrypted_data']),
                hmac_sig=bytes(note['hmac_signature']),
                key=ENCRYPTION_KEY,
                expected_owner=g.current_user['id']
            )
            if decrypted is not None:
                result.append({
                    "note_id": note['id'],
                    "note": decrypted,
                    "created_at": note['created_at'].isoformat() if note.get('created_at') else None
                })
        except Exception as e:
            logger.error(f"Note decryption error: {e}")
            continue

    return jsonify({"notes": result})

@app.route('/api/notes/export', methods=['GET'])
@require_auth
def export_notes():
    order_id = request.args.get('order_id', type=int)

    if order_id:
        notes = db_query(
            "SELECT id, order_id, encrypted_data, hmac_signature FROM order_notes WHERE order_id = %s",
            (order_id,), fetchall=True
        )
    else:
        notes = db_query(
            "SELECT id, order_id, encrypted_data, hmac_signature FROM order_notes WHERE customer_id = %s",
            (g.current_user['id'],), fetchall=True
        )

    result = []
    for note in (notes or []):
        blob = export_note_blob(bytes(note['encrypted_data']), bytes(note['hmac_signature']))
        result.append({"note_id": note['id'], "order_id": note['order_id'], "blob": blob})
    return jsonify({"exports": result})

@app.route('/api/notes/import', methods=['POST'])
@require_auth
def import_notes():
    data     = request.get_json()
    blob_hex = data.get('blob', '')

    if not blob_hex:
        return jsonify({"error": "Blob required"}), 400

    try:
        encrypted_data, hmac_sig = import_note_blob(blob_hex)
    except Exception as e:
        return jsonify({"error": f"Invalid blob format: {e}"}), 400

    try:
        decrypted = decrypt_note(
            encrypted_data=encrypted_data,
            hmac_sig=hmac_sig,
            key=ENCRYPTION_KEY,
            expected_owner=g.current_user['id']
        )
    except ValueError as e:
        return jsonify({"error": f"Integrity check failed: {e}"}), 400

    if decrypted is None:
        return jsonify({"error": "Access denied: you are not the owner of this note"}), 403

    return jsonify({"note": decrypted})


# ── LiveTrack helpers ─────────────────────────────────────────────────────────

LIVETRACK_STATUS = {0x00: 'OK', 0x01: 'ERROR', 0x02: 'AUTH_REQUIRED'}
LIVETRACK_OPS    = {
    'gps_update':    (0x02, 'GPS_UPDATE'),
    'status_change': (0x03, 'STATUS_CHANGE'),
    'chat_send':     (0x04, 'CHAT_SEND'),
    'chat_history':  (0x05, 'CHAT_HISTORY'),
}

def _lt_write_frame(sock, opcode: int, payload: bytes = b''):
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    if len(payload) > 65535:
        raise ValueError('LiveTrack payload too large')
    sock.sendall(bytes([opcode]) + struct.pack('>H', len(payload)) + payload)

def _lt_read_frame(sock):
    header = sock.recv(3)
    if len(header) != 3:
        raise ValueError('Short response from LiveTrack')
    status = header[0]
    length = struct.unpack('>H', header[1:3])[0]
    data   = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ValueError('LiveTrack connection closed mid-frame')
        data += chunk
    return status, data.decode('utf-8', errors='replace')

def _lt_session(username: str = None, password: str = None, commands=None):
    commands  = commands or []
    responses = []
    with socket.create_connection((LIVETRACK_HOST, LIVETRACK_PORT), timeout=4) as sock:
        sock.settimeout(4)
        if username is not None and password is not None:
            _lt_write_frame(sock, 0x01, f'{username}:{password}')
            status, data = _lt_read_frame(sock)
            responses.append({
                'command': 'AUTH', 'status': status,
                'status_text': LIVETRACK_STATUS.get(status, f'0x{status:02x}'), 'data': data,
            })
            if status != 0x00:
                return responses
        for command in commands:
            _lt_write_frame(sock, command['opcode'], command.get('payload', b''))
            status, data = _lt_read_frame(sock)
            responses.append({
                'command': command.get('name', f"OP_0x{command['opcode']:02x}"),
                'status': status,
                'status_text': LIVETRACK_STATUS.get(status, f'0x{status:02x}'),
                'data': data,
            })
    return responses



@app.route('/api/livetrack/ping', methods=['GET'])
def livetrack_ping():
    try:
        responses = _lt_session(commands=[{'opcode': 0x10, 'name': 'PING', 'payload': b''}])
        ok = responses and responses[-1]['status'] == 0x00
        return jsonify({'responses': responses}), 200 if ok else 502
    except Exception as e:
        logger.error(f'LiveTrack ping failed: {e}')
        return jsonify({'error': str(e)}), 502

@app.route('/api/livetrack/action', methods=['POST'])
@require_auth
def livetrack_action():
    data     = request.get_json() or {}
    action   = data.get('action', '')
    password = data.get('password', '')

    if not password:
        return jsonify({'error': 'Password required for LiveTrack AUTH'}), 400
    if action not in LIVETRACK_OPS:
        return jsonify({'error': 'Unknown action'}), 400

    opcode, name = LIVETRACK_OPS[action]
    delivery_id  = data.get('delivery_id')

    if action == 'gps_update':
        lat, lon = data.get('lat'), data.get('lon')
        if delivery_id is None or lat is None or lon is None:
            return jsonify({'error': 'delivery_id, lat, and lon required'}), 400
        payload = f'{delivery_id}:{lat},{lon}'
    elif action == 'status_change':
        new_status = data.get('status', '')
        if delivery_id is None or not new_status:
            return jsonify({'error': 'delivery_id and status required'}), 400
        payload = f'{delivery_id}:{new_status}'
    elif action == 'chat_send':
        message = data.get('message', '')
        if delivery_id is None or not message:
            return jsonify({'error': 'delivery_id and message required'}), 400
        payload = f'{delivery_id}:{message}'
    elif action == 'chat_history':
        if delivery_id is None:
            return jsonify({'error': 'delivery_id required'}), 400
        payload = str(delivery_id)

    try:
        responses = _lt_session(
            username=g.current_user['username'],
            password=password,
            commands=[{'opcode': opcode, 'name': name, 'payload': payload}],
        )
        ok = responses and responses[-1]['status'] == 0x00
        return jsonify({'responses': responses}), 200 if ok else 400
    except Exception as e:
        logger.error(f'LiveTrack action failed: {e}')
        return jsonify({'error': str(e)}), 502

def _lt_read_frame_raw(sock):
    header = b''
    while len(header) < 3:
        chunk = sock.recv(3 - len(header))
        if not chunk:
            raise ValueError('LiveTrack connection closed')
        header += chunk
    status = header[0]
    length = struct.unpack('>H', header[1:3])[0]
    data   = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ValueError('LiveTrack connection closed mid-frame')
        data += chunk
    return header + data

@app.route('/api/livetrack/raw', methods=['POST'])
@require_auth
def livetrack_raw():
    data       = request.get_json() or {}
    frames_hex = data.get('frames', [])

    if not frames_hex or not isinstance(frames_hex, list):
        return jsonify({'error': 'frames must be a non-empty list of hex strings'}), 400

    raw_frames = []
    for i, fhex in enumerate(frames_hex):
        try:
            raw_frames.append(bytes.fromhex(fhex))
        except ValueError:
            return jsonify({'error': f'Frame {i} is not valid hex'}), 400

    try:
        responses_hex = []
        with socket.create_connection((LIVETRACK_HOST, LIVETRACK_PORT), timeout=6) as sock:
            sock.settimeout(6)
            for raw_frame in raw_frames:
                sock.sendall(raw_frame)
                responses_hex.append(_lt_read_frame_raw(sock).hex())
        return jsonify({'responses': responses_hex})
    except Exception as e:
        logger.error(f'LiveTrack raw proxy error: {e}')
        return jsonify({'error': str(e)}), 502



@app.route('/api/health', methods=['GET'])
def health():
    try:
        db_query("SELECT 1", fetchone=True)
        return jsonify({"status": "healthy", "service": "OverEats"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/api/cleanup', methods=['POST'])
@require_auth
def cleanup():
    run_cleanup()
    return jsonify({"status": "cleaned"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
