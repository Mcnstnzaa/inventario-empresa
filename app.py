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

# --- FUNCIÓN DE ALERTA POR CORREO ---
def enviar_alerta_correo(nombre_producto, cantidad_actual, stock_minimo):
    remitente = "tu_correo@gmail.com"       
    password = "abcd efgh ijkl mnop"        
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

@app.route('/menu')
def menu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('menu.html')

@app.route('/stock')
def stock():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    conn.close()
    return render_template('stock.html', productos=productos)

@app.route('/alertas')
def alertas():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos WHERE cantidad <= stock_minimo ORDER BY nombre").fetchall()
    conn.close()
    return render_template('alertas.html', productos=productos)

@app.route('/form_ingreso')
def form_ingreso():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    categorias = [row['categoria'] for row in conn.execute("SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria").fetchall()]
    conn.close()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    return render_template('form_ingreso.html', productos=productos, categorias=categorias, fecha_hoy=fecha_hoy)

@app.route('/form_venta')
def form_venta():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    categorias = [row['categoria'] for row in conn.execute("SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria").fetchall()]
    conn.close()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    return render_template('form_venta.html', productos=productos, categorias=categorias, fecha_hoy=fecha_hoy)

@app.route('/accion', methods=['POST'])
def accion():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        producto_id = request.form.get('producto_id')
        cantidad = request.form.get('cantidad')
        tipo = request.form.get('tipo')
        fecha_formulario = request.form.get('fecha_accion')
        metodo_pago = request.form.get('metodo_pago', '')
        precio_venta = request.form.get('precio_venta')
        
        if not producto_id or not cantidad:
            flash('Error: Faltan datos del producto o la cantidad.', 'danger')
            return redirect(url_for('menu'))

        cantidad = int(cantidad)
        conn = get_db()
        p = conn.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
        
        if p:
            if tipo == 'venta' and p['cantidad'] < cantidad:
                flash(f'Error: No puedes vender {cantidad}. Solo hay {p["cantidad"]} en stock.', 'danger')
            else:
                nueva_cantidad = p['cantidad'] + cantidad if tipo == 'ingreso' else p['cantidad'] - cantidad
                
                if fecha_formulario:
                    fecha = datetime.strptime(fecha_formulario, '%Y-%m-%d').strftime("%Y-%m-%d")
                else:
                    fecha = datetime.now().strftime("%Y-%m-%d")
                    
                hora_actual = datetime.now().strftime("%H:%M")
                
                if tipo == 'venta':
                    precio_final = float(precio_venta) if precio_venta else p['precio']
                    fecha_completa = f"{fecha} {hora_actual} | Cant: {cantidad} | Precio: ${precio_final} | Pago: {metodo_pago}"
                    conn.execute("UPDATE productos SET precio = ? WHERE id = ?", (precio_final, producto_id))
                else:
                    fecha_completa = f"{fecha} {hora_actual} | Ingreso"
                
                conn.execute("UPDATE productos SET cantidad = ?, fecha_actualizacion = ? WHERE id = ?",
                             (nueva_cantidad, fecha_completa, producto_id))
                conn.commit()
                
                # El envío de correo está desactivado temporalmente para evitar el "Worker Timeout"
                # if nueva_cantidad <= p['stock_minimo']:
                #     enviar_alerta_correo(p['nombre'], nueva_cantidad, p['stock_minimo'])
                #     flash(f'¡{tipo.capitalize()} registrado! ⚠️ Stock bajo.', 'warning')
                # else:
                #     flash(f'¡{tipo.capitalize()} registrado con éxito!', 'success')

                flash(f'¡{tipo.capitalize()} registrado con éxito!', 'success')
        else:
            flash('Error: Producto no encontrado.', 'danger')
            
        conn.close()
    except Exception as e:
        flash(f'Error en el sistema: {str(e)}', 'danger')
        
    return redirect(url_for('menu'))

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

@app.route('/editar_producto', methods=['POST'])
def editar_producto():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    id_prod = request.form['id_producto']
    nombre = request.form['nombre']
    categoria = request.form['categoria']
    stock_minimo = int(request.form['stock_minimo'])
    precio = float(request.form['precio'])
    
    conn = get_db()
    conn.execute("UPDATE productos SET nombre=?, categoria=?, stock_minimo=?, precio=? WHERE id=?",
                 (nombre, categoria, stock_minimo, precio, id_prod))
    conn.commit()
    conn.close()
    flash('Producto actualizado con éxito', 'success')
    return redirect(url_for('stock'))

@app.route('/eliminar_producto/<int:id>')
def eliminar_producto(id):
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    conn.execute("DELETE FROM productos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Producto eliminado', 'success')
    return redirect(url_for('stock'))

@app.route('/usuarios')
def usuarios():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    lista_usuarios = conn.execute("SELECT * FROM usuarios ORDER BY id").fetchall()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    username = request.form['username'].strip().lower()
    password = request.form['password']
    conn = get_db()
    existe = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
    if existe:
        flash(f'El usuario "{username}" ya existe.', 'danger')
    else:
        conn.execute("INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)",
                     (username, generate_password_hash(password), 'trabajador'))
        conn.commit()
        flash(f'¡Usuario "{username}" creado con éxito!', 'success')
    conn.close()
    return redirect(url_for('usuarios'))

@app.route('/eliminar_usuario/<int:id>')
def eliminar_usuario(id):
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE id = ?", (id,)).fetchone()
    if user and user['rol'] != 'admin':
        conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
        conn.commit()
        flash('Usuario eliminado correctamente', 'success')
    else:
        flash('No puedes eliminar a un administrador', 'danger')
    conn.close()
    return redirect(url_for('usuarios'))

@app.route('/exportar_excel')
def exportar_excel():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = ["ID", "Nombre", "Categoría", "Cantidad", "Stock Mínimo", "Precio", "Fecha / Detalle"]
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

@app.route('/historial_ventas')
def historial_ventas():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    conn = get_db()
    ventas = conn.execute("SELECT * FROM productos WHERE fecha_actualizacion LIKE '%Pago:%' ORDER BY fecha_actualizacion DESC").fetchall()
    conn.close()
    return render_template('historial_ventas.html', ventas=ventas)

@app.route('/descargar_ventas_fechas', methods=['POST'])
def descargar_ventas_fechas():
    if session.get('rol') != 'admin':
        return redirect(url_for('menu'))
    fecha_inicio = request.form['fecha_inicio']
    fecha_fin = request.form['fecha_fin']
    conn = get_db()
    ventas = conn.execute("SELECT * FROM productos WHERE fecha_actualizacion LIKE '%Pago:%' AND fecha_actualizacion >= ? AND fecha_actualizacion <= ? ORDER BY fecha_actualizacion DESC", 
                          (fecha_inicio, fecha_fin + " 23:59")).fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Historial de Ventas"
    headers = ["Producto", "Categoría", "Detalle de la Venta (Cantidad, Precio y Pago)"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="000000")
        
    for row_idx, p in enumerate(ventas, 2):
        ws.cell(row=row_idx, column=1, value=p['nombre'])
        ws.cell(row=row_idx, column=2, value=p['categoria'])
        ws.cell(row=row_idx, column=3, value=p['fecha_actualizacion'])
        
    for i, w in enumerate([30, 20, 60], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name=f"ventas_{fecha_inicio}_a_{fecha_fin}.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
