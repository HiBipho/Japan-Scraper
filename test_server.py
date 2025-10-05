from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "<h1>Server Tes Berjalan!</h1>"

if __name__ == '__main__':
    # Gunakan port 8080 agar sama dengan kasus Anda
    app.run(host='0.0.0.0', port=8080)
