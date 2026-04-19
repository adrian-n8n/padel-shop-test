"""
portal/app.py — Página de entrada al ecosistema Padel Shop Tools
Sirve la pantalla de selección de módulo.
"""
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7002, debug=False)
