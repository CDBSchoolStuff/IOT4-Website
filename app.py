# Imports for Bottle
from bottle import Bottle, run, request, template, auth_basic, HTTPResponse
import bcrypt, sourcetypes

# Imports for database
import sqlite3

# Imports for chart plotting
import random, datetime, datetime, io, base64
import matplotlib.pyplot as plt

####################################################################################################
# Database

try:
    # Forbind til SQLite-databasen (vil oprette databasefilen, hvis den ikke findes)
    db = sqlite3.connect('sensordata.db')

    # Opretter et cursor-objekt til at interagere med databasen
    cursor = db.cursor()

    # Opretter et "table" til at gemme sensor data i
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

    # Gemmer ændringerne og lukker databasen
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

# Eksempel på brug: Generer 10 testdata
generate_test_data(10)


# Hjælpefunktion til at hente data fra databasen
def fetch_sensor_data():
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


@app.route('/')
@auth_basic(check_credentials)
def welcome():
    """Velkomstside, som kræver login."""

    username = request.auth[0]  # Hent brugernavnet fra auth

    welcome_html: sourcetypes.html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Velkommen</title>
        </head>
        <body>
            <h1>Velkommen, {username}!</h1>
            <p>Du er nu logget ind.</p>
            <form action="/logout" method="post">
                <button type="submit">Log ud</button>
            </form>
            <div>{plot()}</div>
        </body>
        </html>
    """
    return template(welcome_html)


@app.route('/plot')
@auth_basic(check_credentials)
def plot():
    # Fetch data from the database
    timestamps, temperatures, humidities, loudness, light_levels = fetch_sensor_data()

    # Create a figure and axis object
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot data
    ax.plot(timestamps, temperatures, label='Temperature (°C)', color='red')
    ax.plot(timestamps, humidities, label='Humidity (%)', color='blue')
    ax.plot(timestamps, loudness, label='Loudness (dB)', color='green')
    ax.plot(timestamps, light_levels, label='Light Level (lux)', color='orange')

    # Format the plot
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('Sensor Values')
    ax.set_title('Sensor Data Visualization')
    ax.legend(loc='upper left')
    ax.grid(True)
    
    # Rotate the x-axis labels for better readability
    plt.xticks(rotation=45, ha="right")
    
    # Convert plot to a PNG image in memory
    img_buf = io.BytesIO()
    plt.tight_layout()  # Adjust layout
    plt.savefig(img_buf, format='png')
    img_buf.seek(0)

    # Convert the PNG image to base64 encoding for embedding in HTML
    img_base64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')
    img_buf.close()

    # Return the image as a data URI for embedding
    return f'<img src="data:image/png;base64,{img_base64}"/>'


@app.route('/logout', method='POST')
def logout():
    """Log brugeren ud ved at sende en HTTP 401, så browseren glemmer credentials."""
    # Send en 401 Unauthorized for at "tvinge" browseren til at glemme login-oplysningerne 
    # (Dette sker først når browseren bliver lukket, hvilket er en kendt begrænsning af denne teknik)
    response = HTTPResponse(status=401)
    response.set_header('WWW-Authenticate', 'Basic realm="Login Required"')
    return response

if __name__ == '__main__':
    # Start serveren (kører lokalt på port 8080)
    run(app, host='localhost', port=8080, debug=True)
