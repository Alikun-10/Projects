CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('customer', 'restaurant', 'driver')),
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS restaurants (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(128) NOT NULL,
    cuisine VARCHAR(64),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS menu_items (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(id),
    name VARCHAR(128) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    available BOOLEAN DEFAULT TRUE
);


CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES users(id),
    restaurant_id INTEGER REFERENCES restaurants(id),
    items JSONB NOT NULL,
    special_instructions TEXT,
    status VARCHAR(32) DEFAULT 'placed'
        CHECK (status IN ('placed','confirmed','preparing','ready','picked_up','delivered','cancelled')),
    total_price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deliveries (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    driver_id INTEGER REFERENCES users(id),
    status VARCHAR(32) DEFAULT 'assigned'
        CHECK (status IN ('assigned','picking_up','on_the_way','delivered')),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    delivery_id INTEGER REFERENCES deliveries(id) ON DELETE CASCADE,
    sender_id INTEGER REFERENCES users(id),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS order_notes (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES users(id),
    encrypted_data BYTEA NOT NULL,
    hmac_signature BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    token VARCHAR(64) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_restaurant ON orders(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_order ON deliveries(order_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_driver ON deliveries(driver_id);
CREATE INDEX IF NOT EXISTS idx_chat_delivery ON chat_messages(delivery_id);
CREATE INDEX IF NOT EXISTS idx_order_notes_customer ON order_notes(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_notes_order ON order_notes(order_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_restaurants_user ON restaurants(user_id);
CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant ON menu_items(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_order_notes_created_at ON order_notes(created_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_created_at ON deliveries(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);



CREATE INDEX IF NOT EXISTS idx_users_created_at
    ON users(created_at);

CREATE INDEX IF NOT EXISTS idx_restaurants_created_at
    ON restaurants(created_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_sender
    ON chat_messages(sender_id);

CREATE OR REPLACE FUNCTION cleanup_old_data() RETURNS void AS $$
DECLARE
    cutoff TIMESTAMP := NOW() - INTERVAL '12 minutes';
BEGIN
    IF NOT pg_try_advisory_xact_lock(7242026) THEN
        RETURN;
    END IF;

    /*
     * Select old users in batches. Everything belonging to these users
     * will be removed, including newer dependent objects.
     */
    CREATE TEMP TABLE cleanup_users ON COMMIT DROP AS
    SELECT id
    FROM users
    WHERE created_at < cutoff
    ORDER BY created_at
    LIMIT 5000;

    CREATE UNIQUE INDEX ON cleanup_users(id);

    /*
     * Include all restaurants owned by selected users, plus a batch of
     * independently old restaurants.
     */
    CREATE TEMP TABLE cleanup_restaurants ON COMMIT DROP AS
    SELECT DISTINCT id
    FROM restaurants
    WHERE user_id IN (
        SELECT id FROM cleanup_users
    )
    OR id IN (
        SELECT id
        FROM restaurants
        WHERE created_at < cutoff
        ORDER BY created_at
        LIMIT 5000
    );

    CREATE UNIQUE INDEX ON cleanup_restaurants(id);

    /*
     * Include all orders associated with selected users/restaurants,
     * plus a batch of independently old orders.
     */
    CREATE TEMP TABLE cleanup_orders ON COMMIT DROP AS
    SELECT DISTINCT id
    FROM orders
    WHERE customer_id IN (
        SELECT id FROM cleanup_users
    )
    OR restaurant_id IN (
        SELECT id FROM cleanup_restaurants
    )
    OR id IN (
        SELECT id
        FROM orders
        WHERE created_at < cutoff
        ORDER BY created_at
        LIMIT 10000
    );

    CREATE UNIQUE INDEX ON cleanup_orders(id);

    /*
     * Include all deliveries belonging to selected orders/users,
     * plus independently old deliveries.
     */
    CREATE TEMP TABLE cleanup_deliveries ON COMMIT DROP AS
    SELECT DISTINCT id
    FROM deliveries
    WHERE order_id IN (
        SELECT id FROM cleanup_orders
    )
    OR driver_id IN (
        SELECT id FROM cleanup_users
    )
    OR id IN (
        SELECT id
        FROM deliveries
        WHERE created_at < cutoff
        ORDER BY created_at
        LIMIT 10000
    );

    CREATE UNIQUE INDEX ON cleanup_deliveries(id);

    /*
     * Delete from the deepest child tables first.
     */
    DELETE FROM chat_messages
    WHERE delivery_id IN (
        SELECT id FROM cleanup_deliveries
    )
    OR sender_id IN (
        SELECT id FROM cleanup_users
    )
    OR id IN (
        SELECT id
        FROM chat_messages
        WHERE created_at < cutoff
        ORDER BY created_at
        LIMIT 20000
    );

    DELETE FROM order_notes
    WHERE order_id IN (
        SELECT id FROM cleanup_orders
    )
    OR customer_id IN (
        SELECT id FROM cleanup_users
    )
    OR id IN (
        SELECT id
        FROM order_notes
        WHERE created_at < cutoff
        ORDER BY created_at
        LIMIT 20000
    );

    DELETE FROM deliveries
    WHERE id IN (
        SELECT id FROM cleanup_deliveries
    );

    DELETE FROM sessions
    WHERE expires_at < NOW()
       OR user_id IN (
           SELECT id FROM cleanup_users
       );

    DELETE FROM orders
    WHERE id IN (
        SELECT id FROM cleanup_orders
    );

    DELETE FROM menu_items
    WHERE restaurant_id IN (
        SELECT id FROM cleanup_restaurants
    );

    DELETE FROM restaurants
    WHERE id IN (
        SELECT id FROM cleanup_restaurants
    );

    DELETE FROM users
    WHERE id IN (
        SELECT id FROM cleanup_users
    );
END;
$$ LANGUAGE plpgsql;
