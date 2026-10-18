from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
import os
import io
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'clave_secreta_super_segura'

def get_db():
    conn = sqlite3.connect('inventario_web.db')
    conn.row_factory = sqlite3.Row
    return conn

def enviar_alerta_correo(nombre_producto, cantidad_actual, stock_minimo):
    # ⚠️ CONFIGURA TU CORREO AQUÍ ⚠️
    remitente = "tu_correo@gmail.com"       
    password = "abcd efgh ijkl mnop"        # Contraseña de aplicación de Gmail
    destinatario = "tu_correo@gmail.com"    
    
    asunto = f"⚠️ ALERTA DE STOCK BAJO: {nombre_producto}"
    cuerpo = f"El producto '{nombre_producto}' ha alcanzado el nivel mínimo.\nQuedan solo: {cantidad_actual} unidades.\nMínimo configurado: {stock_minimo}."
    
    msg = MIMEText(cuerpo)
    msg['Subject'] = asunto
    msg['From'] = remitente
    msg['To'] = destinatario
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.send_message(msg)
        server.quit()
        print(">>> CORREO ENVIADO <<<")
    except Exception as e:
        print(f">>> ERROR CORREO: {e} <<<")

# ================= RUTAS =================

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('menu'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['rol'] = user['rol']
            return redirect(url_for('menu'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- MENÚ PRINCIPAL ---
@app.route('/menu')
def menu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('menu.html')

# --- VISTA DE STOCK (Admin) ---
@app.route('/stock')
def stock():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    conn.close()
    return render_template('stock.html', productos=productos)

# --- VISTA DE ALERTAS (Admin) ---
@app.route('/alertas')
def alertas():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos WHERE cantidad <= stock_minimo ORDER BY nombre").fetchall()
    conn.close()
    return render_template('alertas.html', productos=productos)

# --- FORMULARIOS DE ACCIÓN ---
@app.route('/form_ingreso')
def form_ingreso():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    conn.close()
    return render_template('form_ingreso.html', productos=productos)

@app.route('/form_venta')
def form_venta():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    conn.close()
    return render_template('form_venta.html', productos=productos)

# --- PROCESAR ACCIONES ---
@app.route('/accion', methods=['POST'])
def accion():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    producto_id = request.form['producto_id']
    cantidad = int(request.form['cantidad'])
    tipo = request.form['tipo']
    
    conn = get_db()
    p = conn.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
    
    if p:
        if tipo == 'venta' and p['cantidad'] < cantidad:
            flash(f'Error: Solo hay {p["cantidad"]} en stock.', 'danger')
        else:
            nueva_cantidad = p['cantidad'] + cantidad if tipo == 'ingreso' else p['cantidad'] - cantidad
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("UPDATE productos SET cantidad = ?, fecha_actualizacion = ? WHERE id = ?",
                         (nueva_cantidad, fecha, producto_id))
            conn.commit()
            
            if nueva_cantidad <= p['stock_minimo']:
                enviar_alerta_correo(p['nombre'], nueva_cantidad, p['stock_minimo'])
                flash(f'¡{tipo.capitalize()} registrado! ⚠️ Stock bajo. Aviso enviado al admin.', 'warning')
            else:
                flash(f'¡{tipo.capitalize()} registrado con éxito!', 'success')
            
    conn.close()
    return redirect(url_for('menu'))

# --- CREAR PRODUCTO (Admin) ---
@app.route('/crear_producto', methods=['POST'])
def crear_producto():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    nombre = request.form['nombre']
    categoria = request.form['categoria']
    cantidad = int(request.form['cantidad'])
    stock_minimo = int(request.form['stock_minimo'])
    precio = float(request.form['precio'])
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    conn = get_db()
    conn.execute("INSERT INTO productos (nombre, categoria, cantidad, stock_minimo, precio, fecha_actualizacion) VALUES (?, ?, ?, ?, ?, ?)",
                 (nombre, categoria, cantidad, stock_minimo, precio, fecha))
    conn.commit()
    conn.close()
    flash('Producto creado con éxito', 'success')
    return redirect(url_for('stock'))

# --- EXPORTAR EXCEL ---
@app.route('/exportar_excel')
def exportar_excel():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = ["ID", "Nombre", "Categoría", "Cantidad", "Stock Mínimo", "Precio", "Fecha"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="000000")
        
    for row_idx, p in enumerate(productos, 2):
        ws.cell(row=row_idx, column=1, value=p['id'])
        ws.cell(row=row_idx, column=2, value=p['nombre'])
        ws.cell(row=row_idx, column=3, value=p['categoria'])
        ws.cell(row=row_idx, column=4, value=p['cantidad'])
        ws.cell(row=row_idx, column=5, value=p['stock_minimo'])
        ws.cell(row=row_idx, column=6, value=p['precio'])
        ws.cell(row=row_idx, column=7, value=p['fecha_actualizacion'])
        if p['cantidad'] <= p['stock_minimo']:
            for c in range(1, 8):
                ws.cell(row=row_idx, column=c).fill = PatternFill("solid", fgColor="FFD700")

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name=f"inventario_{datetime.now().strftime('%Y%m%d')}.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)