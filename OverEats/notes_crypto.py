import os
import hmac as hmac_module
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


BLOCK_SIZE = 16


def encrypt_note(owner_id: int, note_text: str, key: bytes) -> tuple:
    
    owner_str = str(owner_id).zfill(10)
    plaintext = f"owner={owner_str}|note={note_text}"
    plaintext_bytes = plaintext.encode('utf-8')

    iv = os.urandom(BLOCK_SIZE)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plaintext_bytes, BLOCK_SIZE))

    encrypted_data = iv + ciphertext

    hmac_sig = hmac_module.new(key, ciphertext, hashlib.sha256).digest()

    return encrypted_data, hmac_sig


def decrypt_note(encrypted_data: bytes, hmac_sig: bytes, key: bytes,
                 expected_owner: int) -> str | None:
   
    if len(encrypted_data) < BLOCK_SIZE + BLOCK_SIZE:
        raise ValueError("Encrypted data too short")

    iv = encrypted_data[:BLOCK_SIZE]
    ciphertext = encrypted_data[BLOCK_SIZE:]

    expected_hmac = hmac_module.new(key, ciphertext, hashlib.sha256).digest()

    if not hmac_module.compare_digest(hmac_sig, expected_hmac):
        raise ValueError("HMAC verification failed - data has been tampered with")

    cipher = AES.new(key, AES.MODE_CBC, iv)
    try:
        plaintext = unpad(cipher.decrypt(ciphertext), BLOCK_SIZE)
    except ValueError:
        raise ValueError("Decryption failed - invalid padding")

    plaintext_str = plaintext.decode('utf-8', errors='replace')

    if not plaintext_str.startswith("owner="):
        raise ValueError("Invalid plaintext format")

    owner_part = plaintext_str[6:16]
    try:
        actual_owner = int(owner_part)
    except ValueError:
        raise ValueError("Invalid owner ID in plaintext")

    if actual_owner != expected_owner:
        return None

    note_start = plaintext_str.find("|note=")
    if note_start == -1:
        raise ValueError("Invalid plaintext format: no note field")

    return plaintext_str[note_start + 6:]


def export_note_blob(encrypted_data: bytes, hmac_sig: bytes) -> str:
   
    return (encrypted_data + hmac_sig).hex()


def import_note_blob(blob_hex: str) -> tuple:
    
    raw = bytes.fromhex(blob_hex)
    if len(raw) < BLOCK_SIZE + BLOCK_SIZE + 32:
        raise ValueError("Blob too short")

    hmac_sig = raw[-32:]
    encrypted_data = raw[:-32]
    return encrypted_data, hmac_sig
