####################################################################################################
# Install requirements

import subprocess
import sys
import os

def install_requirements():
    requirements_file = 'requirements.txt'
    
    if os.path.exists(requirements_file):
        print(f"Fandt {requirements_file}. Installerer depencencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", requirements_file])
        except subprocess.CalledProcessError as e:
            print(f"Der opstod en fejl under installationen af depencencies: {e}")
            sys.exit(1)
    else:
        print(f"{requirements_file} blev ikke fundet! Sørg for, at filen ligger i samme mappe.")
        sys.exit(1)

install_requirements()

####################################################################################################
# Imports

# Imports for Bottle
from bottle import Bottle, run, request, template, auth_basic, HTTPResponse, response
import bcrypt, sourcetypes

# Imports for database
import sqlite3

# Imports for chart plotting
import random, datetime, datetime, io, base64
import matplotlib.pyplot as plt

# General imports
from threading import Thread
import asyncio
import logging
import json


# Backup
from ftplib import FTP
import shutil

# Encryption/Decryption
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend

# MQTT
from amqtt.broker import Broker
from amqtt.client import MQTTClient, ConnectException, ClientException
from amqtt.mqtt.constants import QOS_1, QOS_2

####################################################################################################
# Configuration

logger = logging.getLogger(__name__)
mqtt_client = MQTTClient()  # Opretter klienten

script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"[System] script_dir={script_dir}")

PUBLIC_KEY_PATH = os.path.join(script_dir, "certs", "public_key.pem")
PRIVATE_KEY_PATH = os.path.join(script_dir, "certs", "private_key.pem")

print(f"[System] PUBLIC_KEY_PATH={PUBLIC_KEY_PATH}")
print(f"[System] PRIVATE_KEY_PATH={PRIVATE_KEY_PATH}")

USE_HTTPS = False
GENERATE_TEST_DATA = False
START_MQTT_BROKER = True
START_MQTT_CLIENT = True
USE_CRYPTOGRAPHY = False
DATABASE_BACKUP = True

HOST_ADDRESS = "127.0.0.1"
HOST_PORT = 8080

REFRESH_DELAY = 10 # Hvor ofte siden skal refreshes

DATABASE_PATH = os.path.join(script_dir, "sensordata.db")

MQTT_BROKER_HOST_ADDRESS = "0.0.0.0" # Adresse som MQTT brokeren bliver hostet på (0.0.0.0 binder sig til alle eksterne adresser)
MQTT_BROKER_HOST_PORT = "1883"
MQTT_BROKER_CONNECT_ADDRESS = "mqtt://localhost"  # Adresse som MQTT klienten skal forbinde til (Brug "mqtt://localhost" hvis lokal)
MQTT_TOPIC_SENSORDATA = 'mqtt_sensordata'


MIN_TEMPERATURE, MAX_TEMPERATURE = 17, 19
MIN_HUMIDITY, MAX_HUMIDITY = 40, 60
MIN_LIGHT_LEVEL, MAX_LIGHT_LEVEL = 0.1, 10
MIN_LOUDNESS, MAX_LOUDNESS = 0.1, 30


# Backup constants
FTP_HOST = "localhost"
FTP_USER = "iot4"
FTP_PASSWORD = "awesome123"
BACKUP_DIR = os.path.join(script_dir, "backups")
REMOTE_DIR = "/backups"
DATABASE_BACKUP_DELAY = 60




####################################################################################################
# Database

try:
    # Forbind til SQLite-databasen (vil oprette databasefilen, hvis den ikke findes)
    db = sqlite3.connect(DATABASE_PATH)

    # Opret et cursor-objekt til at interagere med databasen
    cursor = db.cursor()

    # Opret en tabel til at gemme sensor data i
    sql_table_creation: sourcetypes.sql = """
        CREATE TABLE IF NOT EXISTS SensorData (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            humidity REAL,
            loudness REAL,
            light_level REAL
        )
    """
    cursor.execute(sql_table_creation)

    # Gem ændringerne og luk databasen
    db.commit()

    print("[Database] Database og tabel er oprettet succesfuldt!")

except Exception as ex:
    print(ex)

finally:
    # Kører altid efter try eller except, for at sikre at databasen bliver lukket.
    if "db" in locals(): db.close()



def get_current_timestamp():
    """Returnerer den aktuelle tid som String"""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def insert_data_into_database(data: list):
        try:
            # Forbind til SQLite-databasen
            db = sqlite3.connect(DATABASE_PATH)
            cursor = db.cursor()
            
            timestamp = get_current_timestamp() # Aktuel tid

            # Udpak data listen til variabler
            temperature, humidity, loudness, light_level = data

            # Sæt data ind i tabellen
            sql_insert_into_table: sourcetypes.sql = """
                INSERT INTO SensorData (timestamp, temperature, humidity, loudness, light_level)
                VALUES (?, ?, ?, ?, ?)
            """
            cursor.execute(sql_insert_into_table, (timestamp, temperature, humidity, loudness, light_level))

            # Gem ændringer i databasen
            db.commit()

        except Exception as ex:
            print(f"[Database] Der opstod en fejl: {ex}")

        finally:
            # Sørg for at databasen bliver lukket
            if "db" in locals():
                db.close()



def generate_test_data():
    """Funktion der genererer testdata og returnerer det som liste."""

    # Generer testdata
    temperature = round(random.uniform(15.0, 25.0), 2)  # Temperatur mellem 15.0 og 30.0 grader Celsius
    humidity = round(random.uniform(30.0, 90.0), 2)      # Luftfugtighed mellem 30% og 90%
    loudness = round(random.uniform(20.0, 50.0), 2)     # Støjniveau mellem 30 og 100 dB
    light_level = round(random.uniform(0.0, 200.0), 2) # Lysniveau mellem 100 og 1000 lux

    return [temperature, humidity, loudness, light_level]


async def publish_testdata_loop(delay: int, client: MQTTClient):
    """Kører løkke der genererer og publisher testdata med delay"""
    while True:
        await mqtt_publish_data(generate_test_data(), client)
        await asyncio.sleep(delay)


def fetch_sensor_data():
    """Hjælpefunktion til hentning af værdier fra sensordata databasen. Returnerer dem som lister."""
    try:
        # Forbind til databasen
        db = sqlite3.connect(DATABASE_PATH)
        cursor = db.cursor()

        # Hent data fra SensorData tabellen
        sql_get_sensordata_table: sourcetypes.sql = """
            SELECT timestamp, temperature, humidity, loudness, light_level FROM SensorData ORDER BY timestamp DESC LIMIT 100
            """
        
        cursor.execute(sql_get_sensordata_table)
        rows = cursor.fetchall()

        # Luk forbindelsen til databasen
        db.close()

        # Returner data (tidspunkter og sensorværdier)
        timestamps = [row[0] for row in rows]
        temperatures = [row[1] for row in rows]
        humidities = [row[2] for row in rows]
        loudness = [row[3] for row in rows]
        light_levels = [row[4] for row in rows]
        
        return timestamps, temperatures, humidities, loudness, light_levels

    except Exception as ex:
        print(f"[Database] Der opstår en fejl: {ex}")
        return [], [], [], [], []

def get_latest_datapoint(data_type):
    """Finder den nyeste værdi for en valgt datatype fra sensordata."""
    # Henter sensordata fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    # Hvis der ikke er nogen data, så returner bare None
    if not timestamps:
        return None

    # Lav en "ordbog" (dictionary), der forbinder datatype med værdierne
    data_map = {
        "timestamp": timestamps,
        "temperature": temperatures,
        "humidity": humidities,
        "loudness": loudness,
        "light_level": light_levels
    }

    # Tjek om den ønskede datatype findes
    if data_type in data_map:
        return data_map[data_type][0]  # Returner den nyeste værdi
    else:
        # Hvis det er noget andet end de gyldige datatyper, brok dig
        raise ValueError(f"Ugyldig datatype: {data_type}. Vælg mellem 'timestamp', 'temperature', 'humidity', 'loudness', eller 'light_level'.")



####################################################################################################
# Database Backup and FTP sending

def create_database_backup(db_path, backup_dir):
    """
    Laver en backup af SQLite-databasen.

    Parametre:
        db_path (str): Stien til SQLite-databasen.
        backup_dir (str): Lokalt bibliotek hvor backup'en gemmes.

    Returnerer:
        str: Stien til den oprettede backup-fil.
    """

    try:
        # Få dato og tidspunkt til backup-filnavnet
        current_date = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_filename = f"sensordata_backup_{current_date}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Sørg for at backup-biblioteket eksisterer, ellers lav det
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        # Kopier databasen til backup-stien
        shutil.copy(db_path, backup_path)
        print(f"[Backup] Backup lavet: '{backup_path}'")

        return backup_path
    except Exception as e:
        print(f"[Backup] Der skete en fejl under backup: {e}")
        raise


def upload_to_ftp(ftp_host, ftp_user, ftp_password, file_path, remote_dir):
    """
    Uploader en fil til en FTP-server.

    Parametre:
        ftp_host (str): FTP-serverens adresse.
        ftp_user (str): Brugernavnet til FTP-serveren.
        ftp_password (str): Adgangskoden til FTP-serveren.
        file_path (str): Stien til filen der skal uploades.
        remote_dir (str): Mappen på FTP-serveren hvor filen uploades.
    """
    try:
        # Forbind til FTP-serveren
        ftp = FTP(ftp_host)
        ftp.login(user=ftp_user, passwd=ftp_password)
        print(f"[FTP] Tilsluttet FTP-serveren: {ftp_host}")

        # Skift til den fjernmappe, hvis den er angivet
        if remote_dir:
            ftp.cwd(remote_dir)

        # Åbn filen og upload den
        with open(file_path, 'rb') as file:
            ftp.storbinary(f'STOR {os.path.basename(file_path)}', file)
            print(f"[FTP] Fil uploadet til '{remote_dir}/{os.path.basename(file_path)}'.")

        # Luk forbindelsen
        ftp.quit()
        print("[FTP] FTP-forbindelsen er lukket.")
    except Exception as e:
        print(f"[FTP] Der skete en fejl under upload: {e}")
        raise


####################################################################################################
# Graph Plotting

def plot(selected_metrics=None, title=None, lower_threshold=None, upper_threshold=None):
    """
    Plot specifikke sensordata og returner grafen som en base64-kodet streng.

    selected_metrics (dict): 
    En dictionary hvor keys er navnene på de datapunkter, der skal plottes (fx 'Temperature', 'Humidity'), og værdierne er tuples med (data_values, label, color).
   
    Eksempel: 
    {
        "Temperature": (temperatures, "Temperature (°C)", "red"),
        "Humidity": (humidities, "Humidity (%)", "blue"),
    }
    """

    # Hent data fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    # Hvis der ikke er valgt nogle datapunkter, så vælges alle som standard
    if selected_metrics is None:

        selected_metrics = {
            "Temperature": (temperatures, "Temperature (°C)", "red"),
            "Humidity": (humidities, "Humidity (%)", "blue"),
            "Loudness": (loudness, "Loudness (dB)", "green"),
            "Light Level": (light_levels, "Light Level (lux)", "orange"),
        }

    
    
    # Opret en figur og en akse
    fig, ax = plt.subplots(figsize=(10, 6))

    # Loop gennem valgte datapunkter og plot dem
    for metric_name, (data, label, color) in selected_metrics.items():
        ax.plot(timestamps, data, label=label, color=color)


    if lower_threshold and upper_threshold:
        # Fill the area between the thresholds
        plt.fill_between(timestamps, lower_threshold, upper_threshold, color='green', alpha=0.3, label='Ideele soveforhold')
        plt.axhline(y=lower_threshold, color='black', linestyle='--', linewidth=1)
        plt.axhline(y=upper_threshold, color='black', linestyle='--', linewidth=1)
    elif upper_threshold and not lower_threshold:
        plt.axhline(y=upper_threshold, color='black', linestyle='--', linewidth=1, label='Ideele soveforhold')


    # Formater grafen lidt
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('Sensorværdier')
    if title is None:
        ax.set_title('Sensor Data Visualisering')
    else:
        ax.set_title(title)
    ax.legend(loc='upper left')  # Tilføj en lille forklaring i hjørnet
    ax.grid(True)  # Tænd for gitter, så det er nemmere at læse

    # Drej x-aksens labels, så de ikke overlapper og er til at læse. Desuden begræns x-axis labels til hver 10.
    plt.xticks(rotation=45, ha="right", ticks=range(0, 100, 10))
    
    # Konverter grafen til et PNG-billede i hukommelsen
    img_buf = io.BytesIO()
    plt.tight_layout()  # Sørg for layoutet er pænt
    plt.savefig(img_buf, format='png')
    img_buf.seek(0)

    # Konverter PNG-billedet til base64, så det kan bruges i HTML
    img_base64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')
    img_buf.close()

    # Returner billedet som en base64-streng
    return img_base64



####################################################################################################
# Encryption/Decryption

def load_public_key_from_file(path_to_public_key):
    """Indlæs public_key fra fil."""
    with open(path_to_public_key, "rb") as key_file:
        public_key = serialization.load_pem_public_key(
            key_file.read(),
            backend=default_backend()
        )
    return public_key


def load_private_key_from_file(path_to_private_key, password=None):
    """Indlæs private_key fra fil."""
    with open(path_to_private_key, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=password,  # Sker ikke noget hvis der ikke er sat noget password
            backend=default_backend()
        )
    return private_key


def encrypt_message(byte_string_message):
    
    # Indlæs public_key
    public_key = load_public_key_from_file(PUBLIC_KEY_PATH)

    # Encrypter besked
    encrypted_message = public_key.encrypt(
        byte_string_message,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
            )
        )
    print(f"[Crypto] Encrypted Message: {encrypted_message}")
    return encrypted_message
    
    

def decrypt_message(encrypted_message: bytearray, password=None):
    
    # Indlæs private_key
    private_key = load_private_key_from_file(PRIVATE_KEY_PATH, password)

    # Konverter bytearray til bytes hvis nødvendigt
    if isinstance(encrypted_message, bytearray):
        encrypted_message = bytes(encrypted_message)

    decrypted_message = private_key.decrypt(
        encrypted_message,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return decrypted_message

####################################################################################################
# MQTT Client

# https://amqtt.readthedocs.io/en/latest/references/mqttclient.html

def make_byte_string(input):
    return json.dumps(input).encode('utf-8')


async def mqtt_publish_data(data: list, client: MQTTClient):
    """Takes sensordata and publishes it to MQTT topic. Simulating the sensor device sending."""

    byte_string = make_byte_string(data)

    if USE_CRYPTOGRAPHY:
        byte_string = encrypt_message(byte_string)
    
    message = await client.publish(MQTT_TOPIC_SENSORDATA, byte_string)

    print(message)
    print("[MQTT Client] Message published")


# Callback: Håndterer modtagne beskeder
async def on_message(client: MQTTClient):
 #   try:
        print("[MQTT Client] Venter på beskeder...")  # Venter på beskeder fra broker
        while True:
            # Hent næste besked
            message = await client.deliver_message()
            packet = message.publish_packet

            # Dekod beskedens indhold
            topic = packet.variable_header.topic_name
            payload = packet.payload.data

            # Filtrér beskeder for den rigtige topic
            if topic == MQTT_TOPIC_SENSORDATA:
                try:
                    if USE_CRYPTOGRAPHY:
                        # Dekrypter payload
                        decrypted_payload = decrypt_message(payload)
                        payload_str = decrypted_payload.decode("utf-8")
                    else:
                        payload_str = payload.decode("utf-8")
                    
                    # Konverter payload string tilbage til en liste.
                    converted_list = eval(payload_str)

                    print(f"[MQTT Client] Modtaget besked på topic '{topic}': {converted_list}")

                    # Indsæt modtaget data i databasen.
                    insert_data_into_database(converted_list)
                    print("[MQTT Client] Sensordata indsat i databasen.")
                except Exception as e:
                    print(f"[MQTT Client] Fejl ved behandling af payload: {e}")

    # except Exception as e:
    #     print(f"[MQTT Client] Fejl ved modtagelse af besked: {e}")


# Funktion: Starter MQTT-klienten og håndterer forbindelsen
async def start_mqtt_client(client: MQTTClient):
    try:
        print("[MQTT Client] Forbinder til broker...")  # Forbinder til broker
        await client.connect(MQTT_BROKER_CONNECT_ADDRESS)
        print("[MQTT Client] Forbundet til broker.")

        # Abonner på den ønskede topic
        await client.subscribe([(MQTT_TOPIC_SENSORDATA, 1)])  # QoS 0
        print(f"[MQTT Client] Abonneret på topic: {MQTT_TOPIC_SENSORDATA}")

        # Start med at lytte efter beskeder
        await on_message(client)

    except ConnectException as ce:
        print(f"[MQTT Client] Kunne ikke forbinde til broker: {ce}")
    except ClientException as e:
        print(f"[MQTT Client] Noget gik galt: {e}")
    finally:
        # Sørg for at disconnecte, når vi er færdige
        await client.disconnect()
        print("[MQTT Client] Forbindelsen lukket.")




####################################################################################################
# Bottle

app = Bottle()

# Brugerliste med hashed adgangskoder
users = {
    "admin": bcrypt.hashpw(b"password123", bcrypt.gensalt()),
    "christian": bcrypt.hashpw(b"password321", bcrypt.gensalt()),
    "magnus": bcrypt.hashpw(b"password213", bcrypt.gensalt())
}

def check_credentials(username, password):
    """Tjek om brugernavn og adgangskode er gyldige."""
    if username in users:
        # Tjek adgangskode mod det hashed kodeord
        return bcrypt.checkpw(password.encode('utf-8'), users[username])
    return False



base_template: sourcetypes.html = """
    <!DOCTYPE html>

    <!--Bootstrap CDN-->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>

    <html lang="da">
    <head>
        <!--<meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">-->
        <title>{{title}}</title>
        <!--<link rel="stylesheet" href="/static/styles.css">-->

        <!-- <script>
            // SSE to automatically update the image (Server-sent events)
            const eventSource = new EventSource('/stream');
            eventSource.onmessage = function(event) {{
                document.getElementById('dynamic-image').src = "data:image/png;base64," + event.data;
            }};
        </script> -->
        <meta http-equiv="refresh" content={{refresh_delay}}> <!-- Refresh every 15 minutes -->

        <style>
            .green {
                color: green;
            }
            .orange {
                color: orange;
            }
            .red {
                color: red;
            }
        </style>

    </head>
    <body>
        <header>
            <nav class="navbar navbar-expand-lg bg-body-tertiary">
                <div class="container-fluid">
                    <a class="navbar-brand" href="/">Smart Night</a>
                    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavDropdown" aria-controls="navbarNavDropdown" aria-expanded="false" aria-label="Toggle navigation">
                        <span class="navbar-toggler-icon"></span>
                    </button>
                    <div class="collapse navbar-collapse" id="navbarNavDropdown">
                        <ul class="navbar-nav">
                            <li class="nav-item">
                                <a class="nav-link active" aria-current="page" href="/">Home</a>
                            </li>
                            <li class="nav-item dropdown">
                                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                    Forhold i soveværelset
                                </a>
                                <ul class="dropdown-menu">
                                    <li><a class="dropdown-item" href="temperature">Temperatur</a></li>
                                    <li><a class="dropdown-item" href="humidity">Luftfugtighed</a></li>
                                    <li><a class="dropdown-item" href="light_level">Lys</a></li>
                                    <li><a class="dropdown-item" href="loudness">Støj</a></li>
                                </ul>
                            </li>
                        </ul>
                        <div class="d-flex ms-auto">
                            <form action="/logout" method="post" class="d-inline">
                                <button type="submit" class="btn btn-outline-danger">Log ud</button>
                            </form>
                        </div>
                    </div>
                </div>
            </nav>

        </header>
        <main class="flex-grow-1">
            <br>
            <div class="container-sm">
                {{! content }}
            </div>
        </main>
        <footer class="mt-auto">
            <br>
            <p>&copy; 2024 IOT4 Project - Smart Night</p>
        </footer>
    </body>
    </html>
"""

# Function to "inherit" base template
def render_page(content, title):
    """Combine the base template with page-specific content."""
    return template(base_template, title=title, content=content, refresh_delay=REFRESH_DELAY)


def determine_color_class(value, min, max):
    # Determine the color class (green for within range, orange for out of range)
    return "green" if min <= value <= max else "orange"

def get_time_since_data():
    # Hent data fra databasen
    latest_timestamp = get_latest_datapoint("timestamp")
    current_time = get_current_timestamp()

    timestamp1 = datetime.datetime.strptime(latest_timestamp, '%Y-%m-%d %H:%M:%S')
    timestamp2 = datetime.datetime.strptime(current_time, '%Y-%m-%d %H:%M:%S')

    time_diff = timestamp2 - timestamp1

    minutes_diff = int(time_diff.total_seconds() / 60)

    return minutes_diff


@app.route('/')
@auth_basic(check_credentials)
def welcome_page():
    """Velkomstside, som kræver login."""

    username = request.auth[0]  # Hent brugernavnet fra auth
    alldata_base64_plot = plot()

    latest_temperature = float(get_latest_datapoint("temperature"))
    latest_humidity = float(get_latest_datapoint("humidity"))
    latest_light_level = float(get_latest_datapoint("light_level"))
    latest_loudness = float(get_latest_datapoint("loudness"))

    temperature_color = determine_color_class(latest_temperature, MIN_TEMPERATURE, MAX_TEMPERATURE)
    humidity_color = determine_color_class(latest_humidity, MIN_HUMIDITY, MAX_HUMIDITY)
    light_level_color = determine_color_class(latest_light_level, MIN_LIGHT_LEVEL, MAX_LIGHT_LEVEL)
    loudness_color = determine_color_class(latest_loudness, MIN_LOUDNESS, MAX_LOUDNESS)

    welcome_content: sourcetypes.html = f"""
        <h2>Velkommen, {username.capitalize()}!</h2>
        <p>Du er nu logget ind og kan dermed se alle data omkring forholdende i dit soveværelse!</p>

    
        <div class="card-group">
            <div class="card">
                <div class="card-body">
                <h5 class="card-title">Temperatur</h5>
                <h2 class="card-text {temperature_color}">{latest_temperature} °C</h2>
                <p class="card-text"><small class="text-body-secondary">Sidst opdateret {get_time_since_data()} min siden</small></p>
                </div>
            </div>
            <div class="card">
                <div class="card-body">
                <h5 class="card-title">Luftfugtighed</h5>
                <h2 class="card-text {humidity_color}">{latest_humidity} %</h2>
                <p class="card-text"><small class="text-body-secondary">Sidst opdateret {get_time_since_data()} min siden</small></p>
                </div>
            </div>
            <div class="card">
                <div class="card-body">
                <h5 class="card-title">Lys</h5>
                <h2 class="card-text {light_level_color}">{latest_light_level} lux</h2>
                <p class="card-text"><small class="text-body-secondary">Sidst opdateret {get_time_since_data()} min siden</small></p>
                </div>
            </div>
            <div class="card">
                <div class="card-body">
                <h5 class="card-title">Støj</h5>
                <h2 class="card-text {loudness_color}">{latest_loudness} dB</h2>
                <p class="card-text"><small class="text-body-secondary">Sidst opdateret {get_time_since_data()} min siden</small></p>
                </div>
            </div>
        </div>

        <img class="img-fluid" src="data:image/png;base64,{alldata_base64_plot}"/>
    """
    return render_page(welcome_content, title="Velkommen")



def sensor_content_stitcher(key: str, label: str, color, title: str, lower_threshold: float, upper_threshold: float, data, latest_value=0, symbol=""):
    """"""

    selected_metrics = {key: (data, label, color)}
    base64_plot = plot(selected_metrics, title, lower_threshold, upper_threshold)

    color_class = determine_color_class(latest_value, lower_threshold, upper_threshold)

    content: sourcetypes.html = f"""
        <h2>{title}</h2>
        <br>
        <div class="card-group">
            <div class="card">
                <div class="card-body">
                    <h1 class="card-text {color_class}">{latest_value} {symbol}</h2>
                    <p class="card-text"><small class="text-body-secondary">Sidst opdateret {get_time_since_data()} min siden</small></p>
                </div>
            </div>
        </div>
        <br>
        <img class="img-fluid" src="data:image/png;base64,{base64_plot}"/>
    """
    return content


@app.route('/temperature')
@auth_basic(check_credentials)
def temperature_page():
    """Side for temperatur, kræver login."""

    # Hent data fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    TITLE = "Temperatur i soveværelset"

    return render_page(
        sensor_content_stitcher(
            key = "Temperature", 
            label = "Temperatur (°C)", 
            color = "red", 
            title = TITLE, 
            lower_threshold = MIN_TEMPERATURE, 
            upper_threshold = MAX_TEMPERATURE, 
            data = temperatures,
            latest_value = get_latest_datapoint("temperature"),
            symbol = "°C"
        ), 
        title = TITLE
    )



@app.route('/humidity')
@auth_basic(check_credentials)
def temperature_page():
    """Side for luftfugtighed, kræver login."""

    # Hent data fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    title = "Luftfugtighed i soveværelset"
    key = "Humidity"
    label = "Luftfugtighed (%)" 
    color = "blue"
    lower_threshold = MIN_HUMIDITY
    upper_threshold = MAX_HUMIDITY
    latest_value = get_latest_datapoint("humidity")
    symbol = "%"

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, humidities, latest_value, symbol), title)



@app.route('/light_level')
@auth_basic(check_credentials)
def light_level_page():
    """Side for lys niveau, kræver login."""

    # Hent data fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    title = "Lys i soveværelset"
    key = "Light Level"
    label = "Lys (lux)" 
    color = "orange"
    lower_threshold = MIN_LIGHT_LEVEL
    upper_threshold = MAX_LIGHT_LEVEL
    latest_value = get_latest_datapoint("light_level")
    symbol = "lux"

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, light_levels, latest_value, symbol), title)





@app.route('/loudness')
@auth_basic(check_credentials)
def loudness_page():
    """Side for støj, kræver login."""

    # Hent data fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    title = "Støj i soveværelset"
    key = "Loudness"
    label = "Loudness (dB)" 
    color = "green"
    lower_threshold = MIN_LOUDNESS
    upper_threshold = MAX_LOUDNESS
    latest_value = get_latest_datapoint("loudness")
    symbol = "dB"

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, loudness, latest_value, symbol), title)


@app.route('/logout', method='POST')
def logout():
    """Log brugeren ud ved at sende en HTTP 401, så browseren glemmer credentials."""
    # Send en 401 Unauthorized for at "tvinge" browseren til at glemme login-oplysningerne 
    # (Dette sker først når browseren bliver lukket, hvilket er en kendt begrænsning af denne teknik)
    response = HTTPResponse(status=401)
    response.set_header('WWW-Authenticate', 'Basic realm="Login Required"')
    return response



def run_bottle_server():
    """Start Bottle serveren."""
    run(app, host=HOST_ADDRESS, port=HOST_PORT, debug=True, reloader=False)


####################################################################################################
# MQTT Broker

# https://amqtt.readthedocs.io/en/latest/references/broker.html

# Konfiguration til MQTT-brokeren
broker_config = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": f"{MQTT_BROKER_HOST_ADDRESS}:{MQTT_BROKER_HOST_PORT}"
        }
    },
    "auth": {
        "allow-anonymous": True  # Sæt til "False" hvis der skal bruges adgangskode
    },
    "topic-check": {
        "enabled": False, # Kan ikke få til at virke. Så lad den være slået fra.
        "list": [MQTT_TOPIC_SENSORDATA]
    }
}

async def mqtt_broker_coro():
    broker = Broker(broker_config)
    await broker.start()

    print("[MQTT Broker] Running...")
    await asyncio.Event().wait()


####################################################################################################
# Main


async def backup_and_upload_db(delay):
    while True:
        backup_file = create_database_backup(DATABASE_PATH, BACKUP_DIR)
        upload_to_ftp(FTP_HOST, FTP_USER, FTP_PASSWORD, backup_file, REMOTE_DIR)
        await asyncio.sleep(delay)

async def main():
    """Executes concurrent tasks."""
    tasks = []

    # Start MQTT-broker
    if START_MQTT_BROKER:
        print("[System] Starter MQTT-broker...")
        tasks.append(asyncio.create_task(mqtt_broker_coro()))

    # Start MQTT-klient
    if START_MQTT_CLIENT:
        print("[System] Venter 4 sekunder med at starte MQTT-klient...")
        await asyncio.sleep(4)  # Vent 4 sekunder før klienten starter
        print("[System] Starter MQTT-klient...")
        tasks.append(asyncio.create_task(start_mqtt_client(mqtt_client)))

    # Start datagenerator
    if GENERATE_TEST_DATA:
        print("[System] Venter 4 sekunder med at generere testdata...")
        await asyncio.sleep(4)  # Vent 4 sekunder før testdata begynder at generere
        print("[System] Starter test-datagenerator...")
        tasks.append(asyncio.create_task(publish_testdata_loop(10, mqtt_client)))
        
    if DATABASE_BACKUP:
        tasks.append(asyncio.create_task(backup_and_upload_db(DATABASE_BACKUP_DELAY)))

    # Afvent alle opgaver
    print("[System] Alle opgaver er startet. Afventer...")
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    server_thread = None
    try:
        # Start Bottle server på seperat thread.
        server_thread = Thread(target=run_bottle_server, daemon=True)
        server_thread.start()

        # Kør asyncio tasks
        asyncio.run(main())
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        asyncio.get_event_loop().stop()
        print("\nProgram terminated.")