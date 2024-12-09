from bottle import Bottle, run, request, template, auth_basic, HTTPResponse
import bcrypt, sourcetypes, sqlite3


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


welcome_html: sourcetypes.html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Velkommen</title>
        </head>
        <body>
            <h1>Velkommen, {{username}}!</h1>
            <p>Du er nu logget ind.</p>
            <form action="/logout" method="post">
                <button type="submit">Log ud</button>
            </form>
        </body>
        </html>
    """

@app.route('/')
@auth_basic(check_credentials)
def welcome():
    """Velkomstside, som kræver login."""
    username = request.auth[0]  # Hent brugernavnet fra auth
    return template(welcome_html, username=username)

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
