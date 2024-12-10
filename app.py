# Imports for Bottle
from bottle import Bottle, run, request, template, auth_basic, HTTPResponse
import bcrypt, sourcetypes

# Imports for database
import sqlite3

# Imports for chart plotting
import random, datetime, datetime, io, base64
import matplotlib.pyplot as plt

# General imports
import os

####################################################################################################
# Configuration

USE_HTTPS = False
GENERATE_TEST_DATA = True

HOST_ADDRESS = "localhost"
HOST_PORT = 8080


####################################################################################################
# Database

try:
    # Forbind til SQLite-databasen (vil oprette databasefilen, hvis den ikke findes)
    db = sqlite3.connect('sensordata.db')

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



def generate_test_data(num_records):
    try:
        # Forbind til SQLite-databasen
        db = sqlite3.connect('sensordata.db')
        cursor = db.cursor()

        # Generer og indsæt testdata
        for _ in range(num_records):
            temperature = round(random.uniform(15.0, 30.0), 2)  # Temperatur mellem 15.0 og 30.0 grader Celsius
            humidity = round(random.uniform(30.0, 90.0), 2)      # Luftfugtighed mellem 30% og 90%
            loudness = round(random.uniform(30.0, 100.0), 2)     # Støjniveau mellem 30 og 100 dB
            light_level = round(random.uniform(100.0, 1000.0), 2) # Lysniveau mellem 100 og 1000 lux
            
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




# Hjælpefunktion til at hente data fra databasen
def fetch_sensor_data():
    """Muliggør hentning af værdier fra sensordata databasen og returneres som en tuple af lister."""
    try:
        # Forbind til databasen
        db = sqlite3.connect('sensordata.db')
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

def plot(selected_metrics=None):
    """
    Plot specifikke sensordata og returner grafen som en base64-kodet streng.

    selected_metrics (dict): 
    En dictionary hvor nøgler er navnene på de datapunkter, der skal plottes (fx 'Temperature', 'Humidity'), og værdierne er tuples med (data_values, label, color).
   
    Eksempel: 
    {
        "Temperature": (temperatures, "Temperature (°C)", "red"),
        "Humidity": (humidities, "Humidity (%)", "blue"),
    }
    """
    # Hent data fra databasen (her kan man evt. tilpasse til sin egen databasehentning)
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    # Hvis der ikke er valgt nogle datapunkter, så vælger vi alle som standard
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

    # Formater grafen lidt
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('Sensorværdier')
    ax.set_title('Sensor Data Visualisering')
    ax.legend(loc='upper left')  # Tilføj en lille forklaring i hjørnet
    ax.grid(True)  # Tænd for gitter, så det er nemmere at læse

    # Drej x-aksens labels, så de ikke overlapper og er til at læse
    plt.xticks(rotation=45, ha="right")
    
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
    </head>
    <body>
        <header>
            <nav class="navbar navbar-expand-lg bg-body-tertiary">
                <div class="container-fluid">
                    <a class="navbar-brand" href="#">Smart Night</a>
                    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavDropdown" aria-controls="navbarNavDropdown" aria-expanded="false" aria-label="Toggle navigation">
                        <span class="navbar-toggler-icon"></span>
                    </button>
                    <div class="collapse navbar-collapse" id="navbarNavDropdown">
                        <ul class="navbar-nav">
                            <li class="nav-item">
                                <a class="nav-link active" aria-current="page" href="">Home</a>
                            </li>
                            <li class="nav-item dropdown">
                                <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                    Sove Forhold
                                </a>
                                <ul class="dropdown-menu">
                                    <li><a class="dropdown-item" href="temperature">Temperatur</a></li>
                                    <li><a class="dropdown-item" href="humidity">Luftfugtighed</a></li>
                                    <li><a class="dropdown-item" href="light">Lys</a></li>
                                    <li><a class="dropdown-item" href="noise">Støj</a></li>
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
def welcome():
    """Velkomstside, som kræver login."""

    username = request.auth[0]  # Hent brugernavnet fra auth
    alldata_base64_plot = plot()

    welcome_content: sourcetypes.html = f"""
        <h2>Velkommen, {username}!</h2>
        <p>Du er nu logget ind.</p>

        <img src="data:image/png;base64,{alldata_base64_plot}"/>
    """
    return render_page(welcome_content, title="Velkommen")


@app.route('/logout', method='POST')
def logout():
    """Log brugeren ud ved at sende en HTTP 401, så browseren glemmer credentials."""
    # Send en 401 Unauthorized for at "tvinge" browseren til at glemme login-oplysningerne 
    # (Dette sker først når browseren bliver lukket, hvilket er en kendt begrænsning af denne teknik)
    response = HTTPResponse(status=401)
    response.set_header('WWW-Authenticate', 'Basic realm="Login Required"')
    return response



if __name__ == '__main__':
    
    if GENERATE_TEST_DATA:
        # Eksempel på brug: Generer 10 testdata (Udkommenter eller fjern ved endelig implementering)
        generate_test_data(20)

    # Tjekker om det nuværende operativ system er UNIX-lignende.
    if USE_HTTPS and os.name == "posix":
        # Start serveren (kører lokalt på port 8080)
        run(app, host=HOST_ADDRESS, port=HOST_PORT , server='gunicorn'
            # , reloader=1 # Kun anvendt med 'gunicorn'
            # , keyfile='key.pem'
            # , certfile='cert.pem'
            )
    
    else:
        # Start serveren (kører lokalt på port 8080)
        run(app, host=HOST_ADDRESS, port=HOST_PORT, debug=True)
        