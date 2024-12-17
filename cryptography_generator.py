# Kør dette script for at generere nye kryptografiske nøgler.
# VIGTIG BEMÆRKNING: Koden fra denne fil kommer 100% fra ChatGPT og er som sådan ikke en del af den størere løsning.

import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Sæt mappen hvor vi gemmer certifikaterne
output_folder = "certs"

# Tjek om mappen findes, ellers lav den
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Lav en RSA privat nøgle
private_key = rsa.generate_private_key(
    public_exponent=65537,  # Det er den typiske værdi for den offentlige eksponent
    key_size=2048           # Nøglestørrelsen i bits (minimum er 2048)
)

# Lav den offentlige nøgle ud fra den private
public_key = private_key.public_key()

# Gør den private nøgle til PEM-format
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
)

# Gør den offentlige nøgle til PEM-format
public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# Sæt filstierne til hvor de skal gemmes
private_key_path = os.path.join(output_folder, "private_key.pem")
public_key_path = os.path.join(output_folder, "public_key.pem")

# Gem den private nøgle i en fil
with open(private_key_path, "wb") as private_file:
    private_file.write(private_pem)

# Gem den offentlige nøgle i en fil
with open(public_key_path, "wb") as public_file:
    public_file.write(public_pem)

print(f"Den private nøgle er gemt her: {private_key_path}")
print(f"Den offentlige nøgle er gemt her: {public_key_path}")
