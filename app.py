import os
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "petcare-chave-local-2026")
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "petcare.db"))

os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tutores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        telefone TEXT NOT NULL,
        email TEXT
    );
    CREATE TABLE IF NOT EXISTS animais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        especie TEXT NOT NULL,
        raca TEXT,
        idade INTEGER,
        tutor_id INTEGER NOT NULL,
        observacoes TEXT,
        FOREIGN KEY (tutor_id) REFERENCES tutores(id) ON DELETE RESTRICT
    );
    CREATE TABLE IF NOT EXISTS consultas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        animal_id INTEGER NOT NULL,
        data_consulta TEXT NOT NULL,
        horario TEXT NOT NULL,
        motivo TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Agendada',
        FOREIGN KEY (animal_id) REFERENCES animais(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS medicamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        quantidade INTEGER NOT NULL DEFAULT 0,
        validade TEXT
    );
    """)
    db.commit()

@app.before_request
def ensure_database():
    init_db()

def ordenar_animais(lista):
    """Algoritmo de ordenação por nome (Selection Sort)."""
    itens = list(lista)
    for i in range(len(itens)):
        menor = i
        for j in range(i + 1, len(itens)):
            if itens[j]["nome"].casefold() < itens[menor]["nome"].casefold():
                menor = j
        itens[i], itens[menor] = itens[menor], itens[i]
    return itens

def buscar_animal_por_nome(nome):
    """Busca linear simples para demonstrar algoritmo de busca."""
    for animal in get_db().execute("SELECT * FROM animais").fetchall():
        if nome.casefold() in animal["nome"].casefold():
            return animal
    return None

@app.route("/")
def index():
    db = get_db()
    total_tutores = db.execute("SELECT COUNT(*) FROM tutores").fetchone()[0]
    total_animais = db.execute("SELECT COUNT(*) FROM animais").fetchone()[0]
    total_consultas = db.execute("SELECT COUNT(*) FROM consultas").fetchone()[0]
    consultas_hoje = db.execute(
        "SELECT COUNT(*) FROM consultas WHERE data_consulta = ?", (date.today().isoformat(),)
    ).fetchone()[0]
    proximas = db.execute("""
        SELECT c.*, a.nome AS animal_nome, a.especie, t.nome AS tutor_nome
        FROM consultas c
        JOIN animais a ON a.id = c.animal_id
        JOIN tutores t ON t.id = a.tutor_id
        WHERE c.data_consulta >= ?
        ORDER BY c.data_consulta, c.horario LIMIT 5
    """, (date.today().isoformat(),)).fetchall()
    return render_template("index.html", total_tutores=total_tutores,
        total_animais=total_animais, total_consultas=total_consultas,
        consultas_hoje=consultas_hoje, proximas=proximas)

@app.route("/tutores")
def tutores():
    termo = request.args.get("q", "").strip()
    db = get_db()
    registros = db.execute("""
        SELECT t.*, COUNT(a.id) AS total_animais
        FROM tutores t LEFT JOIN animais a ON a.tutor_id = t.id
        WHERE t.nome LIKE ? GROUP BY t.id ORDER BY t.nome COLLATE NOCASE
    """, (f"%{termo}%",)).fetchall()
    return render_template("tutores.html", tutores=registros, termo=termo)

@app.route("/tutores/novo", methods=["GET", "POST"])
@app.route("/tutores/<int:tutor_id>/editar", methods=["GET", "POST"])
def tutor_form(tutor_id=None):
    db = get_db()
    tutor = db.execute("SELECT * FROM tutores WHERE id = ?", (tutor_id,)).fetchone() if tutor_id else None
    if tutor_id and not tutor:
        flash("Tutor não encontrado.", "erro")
        return redirect(url_for("tutores"))
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        telefone = request.form.get("telefone", "").strip()
        email = request.form.get("email", "").strip()
        if not nome or not telefone:
            flash("Nome e telefone são obrigatórios.", "erro")
        else:
            if tutor_id:
                db.execute("UPDATE tutores SET nome=?, telefone=?, email=? WHERE id=?",
                           (nome, telefone, email, tutor_id))
                flash("Tutor atualizado com sucesso!", "sucesso")
            else:
                db.execute("INSERT INTO tutores(nome, telefone, email) VALUES(?,?,?)",
                           (nome, telefone, email))
                flash("Tutor cadastrado com sucesso!", "sucesso")
            db.commit()
            return redirect(url_for("tutores"))
    return render_template("tutor_form.html", tutor=tutor)

@app.post("/tutores/<int:tutor_id>/excluir")
def tutor_delete(tutor_id):
    db = get_db()
    try:
        db.execute("DELETE FROM tutores WHERE id = ?", (tutor_id,))
        db.commit()
        flash("Tutor excluído.", "sucesso")
    except sqlite3.IntegrityError:
        flash("Não é possível excluir: este tutor ainda possui animais cadastrados.", "erro")
    return redirect(url_for("tutores"))

@app.route("/animais")
def animais():
    termo = request.args.get("q", "").strip()
    db = get_db()
    registros = db.execute("""
        SELECT a.*, t.nome AS tutor_nome, t.telefone
        FROM animais a JOIN tutores t ON t.id = a.tutor_id
        WHERE a.nome LIKE ? ORDER BY a.id
    """, (f"%{termo}%",)).fetchall()
    registros = ordenar_animais(registros)
    return render_template("animais.html", animais=registros, termo=termo)

@app.route("/animais/novo", methods=["GET", "POST"])
@app.route("/animais/<int:animal_id>/editar", methods=["GET", "POST"])
def animal_form(animal_id=None):
    db = get_db()
    animal = db.execute("SELECT * FROM animais WHERE id=?", (animal_id,)).fetchone() if animal_id else None
    tutores_lista = db.execute("SELECT * FROM tutores ORDER BY nome").fetchall()
    if animal_id and not animal:
        flash("Animal não encontrado.", "erro")
        return redirect(url_for("animais"))
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        especie = request.form.get("especie", "").strip()
        raca = request.form.get("raca", "").strip()
        idade_txt = request.form.get("idade", "").strip()
        tutor_id = request.form.get("tutor_id", "").strip()
        obs = request.form.get("observacoes", "").strip()
        try:
            idade = int(idade_txt) if idade_txt else None
            if idade is not None and idade < 0:
                raise ValueError
        except ValueError:
            idade = -1
        if not nome or not especie or not tutor_id or idade == -1:
            flash("Preencha nome, espécie e tutor. A idade deve ser um número positivo.", "erro")
        else:
            dados = (nome, especie, raca, idade, tutor_id, obs)
            if animal_id:
                db.execute("""UPDATE animais SET nome=?, especie=?, raca=?, idade=?,
                    tutor_id=?, observacoes=? WHERE id=?""", dados + (animal_id,))
                flash("Animal atualizado!", "sucesso")
            else:
                db.execute("""INSERT INTO animais(nome, especie, raca, idade, tutor_id, observacoes)
                    VALUES(?,?,?,?,?,?)""", dados)
                flash("Animal cadastrado!", "sucesso")
            db.commit()
            return redirect(url_for("animais"))
    return render_template("animal_form.html", animal=animal, tutores=tutores_lista)

@app.post("/animais/<int:animal_id>/excluir")
def animal_delete(animal_id):
    db = get_db()
    db.execute("DELETE FROM animais WHERE id=?", (animal_id,))
    db.commit()
    flash("Animal e consultas relacionadas foram excluídos.", "sucesso")
    return redirect(url_for("animais"))

@app.route("/consultas")
def consultas():
    data_filtro = request.args.get("data", "").strip()
    sql = """
        SELECT c.*, a.nome AS animal_nome, a.especie, t.nome AS tutor_nome
        FROM consultas c JOIN animais a ON a.id=c.animal_id
        JOIN tutores t ON t.id=a.tutor_id
    """
    params = []
    if data_filtro:
        sql += " WHERE c.data_consulta = ?"
        params.append(data_filtro)
    sql += " ORDER BY c.data_consulta DESC, c.horario"
    registros = get_db().execute(sql, params).fetchall()
    return render_template("consultas.html", consultas=registros, data_filtro=data_filtro)

@app.route("/consultas/nova", methods=["GET", "POST"])
@app.route("/consultas/<int:consulta_id>/editar", methods=["GET", "POST"])
def consulta_form(consulta_id=None):
    db = get_db()
    consulta = db.execute("SELECT * FROM consultas WHERE id=?", (consulta_id,)).fetchone() if consulta_id else None
    animais_lista = db.execute("SELECT id, nome, especie FROM animais ORDER BY nome").fetchall()
    if consulta_id and not consulta:
        flash("Consulta não encontrada.", "erro")
        return redirect(url_for("consultas"))
    if request.method == "POST":
        animal_id = request.form.get("animal_id", "")
        data_consulta = request.form.get("data_consulta", "")
        horario = request.form.get("horario", "")
        motivo = request.form.get("motivo", "").strip()
        status = request.form.get("status", "Agendada")
        if not animal_id or not data_consulta or not horario or not motivo:
            flash("Preencha todos os campos obrigatórios.", "erro")
        else:
            dados = (animal_id, data_consulta, horario, motivo, status)
            if consulta_id:
                db.execute("""UPDATE consultas SET animal_id=?, data_consulta=?, horario=?,
                    motivo=?, status=? WHERE id=?""", dados + (consulta_id,))
                flash("Consulta atualizada!", "sucesso")
            else:
                db.execute("""INSERT INTO consultas(animal_id, data_consulta, horario, motivo, status)
                    VALUES(?,?,?,?,?)""", dados)
                flash("Consulta agendada!", "sucesso")
            db.commit()
            return redirect(url_for("consultas"))
    return render_template("consulta_form.html", consulta=consulta, animais=animais_lista)

@app.post("/consultas/<int:consulta_id>/excluir")
def consulta_delete(consulta_id):
    db = get_db()
    db.execute("DELETE FROM consultas WHERE id=?", (consulta_id,))
    db.commit()
    flash("Consulta excluída.", "sucesso")
    return redirect(url_for("consultas"))

@app.route("/estoque", methods=["GET", "POST"])
def estoque():
    db = get_db()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        quantidade = request.form.get("quantidade", "0")
        validade = request.form.get("validade", "")
        try:
            quantidade = int(quantidade)
            if not nome or quantidade < 0:
                raise ValueError
            db.execute("INSERT INTO medicamentos(nome, quantidade, validade) VALUES(?,?,?)",
                       (nome, quantidade, validade))
            db.commit()
            flash("Medicamento adicionado ao estoque.", "sucesso")
            return redirect(url_for("estoque"))
        except ValueError:
            flash("Informe nome e quantidade válida.", "erro")
    medicamentos = db.execute("SELECT * FROM medicamentos ORDER BY nome").fetchall()
    return render_template("estoque.html", medicamentos=medicamentos)

@app.post("/estoque/<int:med_id>/excluir")
def medicamento_delete(med_id):
    db = get_db()
    db.execute("DELETE FROM medicamentos WHERE id=?", (med_id,))
    db.commit()
    flash("Medicamento removido.", "sucesso")
    return redirect(url_for("estoque"))

@app.get("/api/animais")
def api_animais():
    registros = get_db().execute("""
        SELECT a.id, a.nome, a.especie, a.raca, a.idade, t.nome AS tutor
        FROM animais a JOIN tutores t ON t.id=a.tutor_id
        ORDER BY a.nome COLLATE NOCASE
    """).fetchall()
    return jsonify([dict(item) for item in registros])

@app.get("/api/tutores")
def api_tutores():
    registros = get_db().execute("SELECT id, nome, telefone, email FROM tutores ORDER BY nome").fetchall()
    return jsonify([dict(item) for item in registros])

@app.errorhandler(404)
def pagina_nao_encontrada(error):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True)
