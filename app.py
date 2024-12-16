# Imports for Bottle
from bottle import Bottle, run, request, template, auth_basic, HTTPResponse, response
import bcrypt, sourcetypes

# Imports for database
import sqlite3

# Imports for chart plotting
import random, datetime, datetime, io, base64
import matplotlib.pyplot as plt

# General imports
import os
from time import sleep
from threading import Thread

# MQTT
from credentials import credentials
import asyncio
from amqtt.broker import Broker

####################################################################################################
# Configuration

USE_HTTPS = False
GENERATE_TEST_DATA = True
START_MQTT_BROKER = True
START_MQTT_CLIENT = True

HOST_ADDRESS = "localhost"
HOST_PORT = 8080

DATABASE_PATH = 'sensordata.db'


MQTT_TOPIC_SENSORDATA = 'mqtt_sensordata'


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

    print("Database og tabel er oprettet succesfuldt!")

except Exception as ex:
    print(ex)

finally:
    # Kører altid efter try eller except, for at sikre at databasen bliver lukket.
    if "db" in locals(): db.close()



async def generate_test_data(num_records, delay):
    """Funktion der genererer placeholder data og indsætter det i databasen."""

    while True:
        try:
            # Forbind til SQLite-databasen
            db = sqlite3.connect(DATABASE_PATH)
            cursor = db.cursor()

            # Generer og indsæt testdata
            for _ in range(num_records):
                temperature = round(random.uniform(15.0, 25.0), 2)  # Temperatur mellem 15.0 og 30.0 grader Celsius
                humidity = round(random.uniform(30.0, 90.0), 2)      # Luftfugtighed mellem 30% og 90%
                loudness = round(random.uniform(20.0, 50.0), 2)     # Støjniveau mellem 30 og 100 dB
                light_level = round(random.uniform(0.0, 200.0), 2) # Lysniveau mellem 100 og 1000 lux
                
                timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Aktuel tid

                # Sæt data ind i tabellen
                sql_insert_into_table: sourcetypes.sql = """
                    INSERT INTO SensorData (timestamp, temperature, humidity, loudness, light_level)
                    VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(sql_insert_into_table, (timestamp, temperature, humidity, loudness, light_level))

            # Gem ændringer i databasen
            db.commit()
            print(f"{num_records} testdata bliver indsat.")

        except Exception as ex:
            print(f"Der opstår en fejl: {ex}")

        finally:
            # Sørg for at databasen bliver lukket
            if "db" in locals():
                db.close()
            await asyncio.sleep(delay)
            #sleep(delay)



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
        print(f"Der opstår en fejl: {ex}")
        return [], [], [], [], []



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
# MQTT Client

# https://github.com/CDBSchoolStuff/IOT3-Point-of-Ordering/blob/83e08c390f011f64f7b18a91e050c7afc1fb731a/app.py#L34C1-L101C61
# https://pypi.org/project/paho-mqtt/

import paho.mqtt.client as mqtt

mqtt_server = credentials['mqtt_server']


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[MQTT Client] Connected with result code {reason_code}")
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(MQTT_TOPIC_SENSORDATA)

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):

    if msg.topic == MQTT_TOPIC_SENSORDATA:
        byte_string = msg.payload
        decoded_string = byte_string.decode("utf-8")
        
        print(f"{msg.topic} {decoded_string}")


async def start_mqtt_client():
    try:
        mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqttc.on_connect = on_connect
        mqttc.on_message = on_message
        mqttc.connect(mqtt_server)

        # Blocking call that processes network traffic, dispatches callbacks and
        # handles reconnecting.
        # Other loop*() functions are available that give a threaded interface and a
        # manual interface.
        # mqttc.loop_forever()
        mqttc.loop_start()

    except Exception as e:
        print(f"[MQTT Client] {e}")
        print("[MQTT Client] Failed to connect to MQTT broker. Continuing...")




####################################################################################################
# Bottle

app = Bottle()

# Brugerliste med hashed adgangskoder
users = {
    "admin": bcrypt.hashpw(b"password123", bcrypt.gensalt())
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

        <script>
            // SSE to automatically update the image (Server-sent events)
            const eventSource = new EventSource('/stream');
            eventSource.onmessage = function(event) {{
                document.getElementById('dynamic-image').src = "data:image/png;base64," + event.data;
            }};
        </script>

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
                    </div>
                </div>
            </nav>

        </header>
        <main>
            <br>
            {{! content }}
        </main>
        <footer>
            <br>
            <p>&copy; 2024 IOT4 Project - Smart Night</p>
        </footer>
    </body>
    </html>
"""

# Function to "inherit" base template
def render_page(content, title):
    """Combine the base template with page-specific content."""
    return template(base_template, title=title, content=content)





@app.route('/')
@auth_basic(check_credentials)
def welcome_page():
    """Velkomstside, som kræver login."""

    username = request.auth[0]  # Hent brugernavnet fra auth
    alldata_base64_plot = plot()

    welcome_content: sourcetypes.html = f"""
        <h2>Velkommen, {username}!</h2>
        <p>Du er nu logget ind og kan dermed se alle data omkring forholdende i dit soveværelse!</p>

        <img src="data:image/png;base64,{alldata_base64_plot}"/>
    """
    return render_page(welcome_content, title="Velkommen")



def sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, data):
    """"""

    selected_metrics = {key: (data, label, color)}
    base64_plot = plot(selected_metrics, title, lower_threshold, upper_threshold)

    content: sourcetypes.html = f"""
        <h2>{title}</h2>
        <br>
        <img src="data:image/png;base64,{base64_plot}"/>
        <img id="dynamic-image" src="data:image/png;base64,{plot(selected_metrics, title, lower_threshold, upper_threshold)}" alt="Loading plot..."/>
        <p>Billedet opdateres automatisk!</p>
    """
    return content


@app.route('/temperature')
@auth_basic(check_credentials)
def temperature_page():
    """Side for temperatur, kræver login."""

    # Hent data fra databasen
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    title = "Temperatur i soveværelset"
    key = "Temperature"
    label = "Temperatur (°C)" 
    color = "red"
    lower_threshold = 17
    upper_threshold = 19

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, temperatures), title)



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
    lower_threshold = 40
    upper_threshold = 60

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, humidities), title)



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
    lower_threshold = 0.1
    upper_threshold = 10

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, light_levels), title)





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
    lower_threshold = 0.1
    upper_threshold = 30

    return render_page(sensor_content_stitcher(key, label, color, title, lower_threshold, upper_threshold, loudness), title)


@app.route('/logout', method='POST')
def logout():
    """Log brugeren ud ved at sende en HTTP 401, så browseren glemmer credentials."""
    # Send en 401 Unauthorized for at "tvinge" browseren til at glemme login-oplysningerne 
    # (Dette sker først når browseren bliver lukket, hvilket er en kendt begrænsning af denne teknik)
    response = HTTPResponse(status=401)
    response.set_header('WWW-Authenticate', 'Basic realm="Login Required"')
    return response



@app.route('/stream')
@auth_basic(check_credentials)
def sse_stream():
    """SSE endpoint to stream the updated plot image."""
    response.content_type = 'text/event-stream'
    response.cache_control = 'no-cache'
    
    # Continuously send the updated plot image as a base64 string
    while True:
        base64_image = plot()  # Generate or fetch the current plot as base64
        yield f"data: {base64_image}\n\n"
        sleep(5)  # Send updates every 5 seconds



####################################################################################################
# MQTT Broker

# Konfiguration til MQTT-brokeren
broker_config = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": "127.0.0.1:1883"  # Her kan du ændre IP og port, hvis du vil
        }
    },
    "sys_interval": 10,  # Tidsinterval for systememner (sys topics)
    "auth": {
        "allow-anonymous": True  # Sæt til False, hvis du vil kræve login
    },
    "topic-check": {
        "enabled": True,
        "list": [MQTT_TOPIC_SENSORDATA]
    }
}

async def start_broker():
    broker = Broker(broker_config)
    await broker.start()

    print("[MQTT Broker] Running...")
    await asyncio.Event().wait()


def run_bottle_server():
    """Start Bottle serveren."""
    run(app, host=HOST_ADDRESS, port=HOST_PORT, debug=True, reloader=False)


####################################################################################################
# Main

async def main():
    """Executes asynchronous tasks."""
    tasks = []

    if START_MQTT_BROKER:
        tasks.append(asyncio.create_task(start_broker()))
    
    if GENERATE_TEST_DATA:
        tasks.append(asyncio.create_task(generate_test_data(1, 10)))
        
    if START_MQTT_CLIENT:
        await asyncio.sleep(4)  # Vent med at starte MQTT client
        tasks.append(asyncio.create_task(start_mqtt_client()))

    # Await all tasks
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    server_thread = None
    try:
        # Start Bottle server på seperat thread.
        server_thread = Thread(target=run_bottle_server, daemon=True)
        server_thread.start()

        # Kør asyncio tasks
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated.")