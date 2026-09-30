import hashlib
from pathlib import Path
import os


def get_hash(file, destination_path):
    hash_chunk_size = 4 * 1024 * 1024
    if os.path.exists(file):
        with open(Path(file), "rb") as f:
            block_hashes = bytearray()
            while True:
                chunk = f.read(hash_chunk_size).replace(b"\r\n", b"").replace(b"\n", b"").replace(b"\r", b"")
                if not chunk:
                    break
                block_hashes += hashlib.sha256(chunk).digest()
        return hashlib.sha256(
            (destination_path + hashlib.sha256(block_hashes).hexdigest()).encode('utf-8')).hexdigest()
    return None
