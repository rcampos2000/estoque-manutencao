"""
app_web.py â Sistema de Controle de PeÃ§as de ReposiÃ§Ã£o (versÃ£o Flask/Web)
CompatÃ­vel com Railway (cloud) e execuÃ§Ã£o local.
"""
import os, io, json
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_file, jsonify)

# ââ Caminhos (cloud-safe) âââââââââââââââââââââââââââââââââââââââââââââââââââââ
APP_DIR  = Path(__file__).parent
DATA_DIR = Path(os.environ.get('DATA_DIR', str(APP_DIR)))

# Em cloud usa /data; localmente usa a mesma pasta do app
import sys
sys.path.insert(0, str(APP_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SobrepÃµe DB_PATH antes de importar database
import database as db
db.DB_PATH = str(DATA_DIR / "estoque_manutencao.db")
db.inicializar_banco()   # garante tabelas mesmo com gunicorn

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'estoque-manutencao-secret-2024')

# ââ Helpers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario_id'):
            return redirect(url_for('login'))
        if session.get('perfil') != 'admin':
            flash('Acesso restrito a administradores.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def fmt_moeda(v):
    try: return f"{float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "0,00"

@app.context_processor
def inject_globals():
    return {'now': datetime.now().strftime('%d/%m/%Y %H:%M'), 'session': session}

# ââ ROTAS: Auth âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/')
def index():
    return redirect(url_for('dashboard') if session.get('usuario_id') else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        user = db.autenticar(request.form['login'], request.form['senha'])
        if user:
            session['usuario_id'] = user['id']
            session['nome']       = user['nome']
            session['perfil']     = user['perfil']
            return redirect(url_for('dashboard'))
        error = 'UsuÃ¡rio ou senha invÃ¡lidos'
    return render_template('login.html', error=error)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# ââ ROTAS: Dashboard ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/dashboard')
@login_required
def dashboard():
    kpis = db.get_kpis()
    kpis['valor_total'] = fmt_moeda(kpis['valor_total'])
    mensal  = [dict(r) for r in db.get_consumo_mensal()]
    top10   = [dict(r) for r in db.get_top_consumo(10)]
    alertas = [dict(r) for r in db.get_alertas_nao_lidos()[:10]]
    return render_template('dashboard.html',
        kpis=kpis, mensal=mensal, top10=top10, alertas=alertas)

# ââ ROTAS: PeÃ§as ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/pecas')
@login_required
def pecas():
    q       = request.args.get('q','')
    cat_id  = request.args.get('cat','')
    critico = 'critico' in request.args
    rows    = db.listar_pecas(filtro=q,
                              categoria_id=int(cat_id) if cat_id else None,
                              apenas_criticos=critico)
    rows    = [dict(r) for r in rows]
    valor_total = fmt_moeda(sum((r['quantidade'] or 0)*(r['custo_unitario'] or 0) for r in rows))
    return render_template('pecas.html', pecas=rows,
        categorias=[dict(c) for c in db.listar_categorias()],
        q=q, cat_id=cat_id, critico=critico, valor_total=valor_total)

@app.route('/pecas/nova', methods=['GET','POST'])
@login_required
def peca_nova():
    if request.method == 'POST':
        f = request.form
        try:
            dados = dict(
                codigo=f['codigo'].strip(), codigo_barras=f.get('codigo_barras','').strip() or None,
                nome=f['nome'].strip(), descricao=f.get('descricao','').strip(),
                categoria_id=int(f['categoria_id']) if f.get('categoria_id') else None,
                fornecedor_id=int(f['fornecedor_id']) if f.get('fornecedor_id') else None,
                localizacao_id=int(f['localizacao_id']) if f.get('localizacao_id') else None,
                unidade=f.get('unidade','UN') or 'UN',
                quantidade=float(f.get('quantidade',0) or 0),
                estoque_minimo=float(f.get('estoque_minimo',1) or 1),
                estoque_maximo=float(f.get('estoque_maximo',100) or 100),
                custo_unitario=float(f.get('custo_unitario',0) or 0),
                preco_venda=float(f.get('preco_venda',0) or 0),
            )
            db.inserir_peca(dados)
            flash('PeÃ§a cadastrada com sucesso!', 'success')
            return redirect(url_for('pecas'))
        except Exception as e:
            flash(f'Erro: {e}', 'error')
    return render_template('peca_form.html', peca=None,
        categorias=[dict(c) for c in db.listar_categorias()],
        fornecedores=[dict(f) for f in db.listar_fornecedores()],
        localizacoes=[dict(l) for l in db.listar_localizacoes()])

@app.route('/pecas/<int:peca_id>/editar', methods=['GET','POST'])
@login_required
def peca_editar(peca_id):
    rows = db.listar_pecas(filtro='')
    peca = next((dict(r) for r in rows if r['id'] == peca_id), None)
    if not peca:
        flash('PeÃ§a nÃ£o encontrada.', 'error')
        return redirect(url_for('pecas'))
    if request.method == 'POST':
        f = request.form
        try:
            dados = dict(
                codigo=f['codigo'].strip(), codigo_barras=f.get('codigo_barras','').strip() or None,
                nome=f['nome'].strip(), descricao=f.get('descricao','').strip(),
                categoria_id=int(f['categoria_id']) if f.get('categoria_id') else None,
                fornecedor_id=int(f['fornecedor_id']) if f.get('fornecedor_id') else None,
                localizacao_id=int(f['localizacao_id']) if f.get('localizacao_id') else None,
                unidade=f.get('unidade','UN') or 'UN',
                estoque_minimo=float(f.get('estoque_minimo',1) or 1),
                estoque_maximo=float(f.get('estoque_maximo',100) or 100),
                custo_unitario=float(f.get('custo_unitario',0) or 0),
                preco_venda=float(f.get('preco_venda',0) or 0),
            )
            db.atualizar_peca(peca_id, dados)
            flash('PeÃ§a atualizada!', 'success')
            return redirect(url_for('pecas'))
        except Exception as e:
            flash(f'Erro: {e}', 'error')
    return render_template('peca_form.html', peca=peca,
        categorias=[dict(c) for c in db.listar_categorias()],
        fornecedores=[dict(f) for f in db.listar_fornecedores()],
        localizacoes=[dict(l) for l in db.listar_localizacoes()])

@app.route('/pecas/<int:peca_id>/excluir', methods=['POST'])
@login_required
def peca_excluir(peca_id):
    db.excluir_peca(peca_id)
    flash('PeÃ§a removida.', 'success')
    return redirect(url_for('pecas'))

@app.route('/pecas/<int:peca_id>/etiqueta')
@login_required
def peca_etiqueta(peca_id):
    """Gera etiqueta PNG com cÃ³digo de barras e QR Code."""
    rows = db.listar_pecas(filtro='')
    peca = next((dict(r) for r in rows if r['id'] == peca_id), None)
    if not peca:
        flash('PeÃ§a nÃ£o encontrada.', 'error')
        return redirect(url_for('pecas'))
    try:
        import barcode as pybr
        from barcode.writer import ImageWriter
        import qrcode
        from PIL import Image, ImageDraw, ImageFont

        W, H = 420, 230
        img  = Image.new("RGB", (W, H), "#ffffff")
        draw = ImageDraw.Draw(img)
        draw.rectangle([0,0,W,44], fill="#1565C0")
        try:
            ft = ImageFont.truetype("arial.ttf", 13)
            fn = ImageFont.truetype("arial.ttf", 12)
            fs = ImageFont.truetype("arial.ttf", 10)
        except:
            ft = fn = fs = ImageFont.load_default()
        draw.text((10,14), "CONTROLE DE ESTOQUE â MANUTENÃÃO INDUSTRIAL", fill="white", font=ft)
        draw.text((10,52), peca['nome'][:48],           fill="#000", font=fn)
        draw.text((10,70), f"CÃ³d: {peca['codigo']}",   fill="#444", font=fs)
        cat = peca.get('categoria_nome') or ''
        loc = peca.get('localizacao_nome') or ''
        draw.text((10,84), f"Cat: {cat}  |  Local: {loc}", fill="#555", font=fs)
        draw.text((10,98), f"Qtd: {peca['quantidade']:.1f} {peca['unidade']}  |  MÃ­n: {peca['estoque_minimo']:.1f}", fill="#555", font=fs)

        barcode_val = peca.get('codigo_barras') or peca['codigo']
        try:
            cls = pybr.get_barcode_class('code128')
            buf = io.BytesIO()
            cls(barcode_val, writer=ImageWriter()).write(buf,
                options={"module_width":0.8,"module_height":8,"write_text":True})
            buf.seek(0)
            bar_img = Image.open(buf).resize((240, 82))
            img.paste(bar_img, (10, 120))
        except Exception:
            draw.text((10,130), f"[ {barcode_val} ]", fill="black", font=fn)

        qr = qrcode.QRCode(box_size=3, border=2)
        qr.add_data(f"COD:{peca['codigo']}|NOME:{peca['nome']}|QTD:{peca['quantidade']}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").resize((85,85))
        img.paste(qr_img, (326, 125))

        buf_out = io.BytesIO()
        img.save(buf_out, 'PNG')
        buf_out.seek(0)
        return send_file(buf_out, mimetype='image/png',
                         as_attachment=True,
                         download_name=f"etiqueta_{peca['codigo']}.png")
    except ImportError:
        flash('Biblioteca de geraÃ§Ã£o de etiqueta nÃ£o disponÃ­vel.', 'error')
        return redirect(url_for('pecas'))

# ââ ROTAS: Busca RÃ¡pida âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/busca')
@login_required
def busca():
    q    = request.args.get('q','').strip()
    peca = None
    if q:
        p = db.buscar_peca_barcode(q)
        if p:
            peca = dict(p)
        else:
            rows = db.listar_pecas(filtro=q)
            if rows: peca = dict(rows[0])
    return render_template('busca.html', q=q, peca=peca)

# ââ ROTAS: MovimentaÃ§Ãµes ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/movimentacoes')
@login_required
def movimentacoes():
    tipo  = request.args.get('tipo','')
    q     = request.args.get('q','')
    di    = request.args.get('di','')
    df    = request.args.get('df','')
    movs  = db.listar_movimentacoes(tipo=tipo or None,
                                    data_inicio=di or None,
                                    data_fim=df or None)
    if q:
        movs = [m for m in movs if q.lower() in (m['peca_nome'] or '').lower()]
    return render_template('movimentacoes.html',
        movs=[dict(m) for m in movs], tipo=tipo, q=q, di=di, df=df)

@app.route('/movimentacoes/nova', methods=['GET','POST'])
@login_required
def mov_nova():
    peca_id = request.args.get('peca_id') or request.form.get('peca_id')
    tipo    = request.args.get('tipo','saida')
    peca    = None
    if peca_id:
        rows = db.listar_pecas(filtro='')
        peca = next((dict(r) for r in rows if str(r['id'])==str(peca_id)), None)
    if request.method == 'POST':
        f = request.form
        try:
            pid = int(f['peca_id'])
            qtd = float(f['quantidade'])
            db.registrar_movimentacao(
                peca_id=pid, tipo=f['tipo'], quantidade=qtd,
                usuario_id=session['usuario_id'],
                equip_id=int(f['equipamento_id']) if f.get('equipamento_id') else None,
                os_num=f.get('os_numero','').strip() or None,
                motivo=f.get('motivo','').strip() or None,
                obs=f.get('observacao','').strip() or None,
            )
            flash(f'MovimentaÃ§Ã£o registrada com sucesso!', 'success')
            return redirect(url_for('pecas'))
        except Exception as e:
            flash(f'Erro: {e}', 'error')
    todas_pecas = [dict(r) for r in db.listar_pecas(filtro='')]
    return render_template('mov_form.html', peca=peca, tipo=tipo,
        todas_pecas=todas_pecas,
        equipamentos=[dict(e) for e in db.listar_equipamentos()])

# ââ ROTAS: Alertas ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/alertas')
@login_required
def alertas():
    return render_template('alertas.html',
        alertas=[dict(a) for a in db.get_alertas_nao_lidos()])

@app.route('/alertas/marcar-lidos', methods=['POST'])
@login_required
def alertas_marcar():
    db.marcar_alertas_lidos()
    flash('Alertas marcados como lidos.', 'success')
    return redirect(url_for('alertas'))

# ââ ROTAS: RelatÃ³rios âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/relatorios')
@login_required
def relatorios():
    return render_template('relatorios.html')

@app.route('/relatorios/estoque-excel')
@login_required
def rel_estoque():
    buf = io.BytesIO()
    db.exportar_estoque_excel(buf)
    buf.seek(0)
    nome = f"estoque_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=nome)

@app.route('/relatorios/movimentacoes-excel')
@login_required
def rel_movimentacoes():
    import openpyxl
    rows = db.listar_movimentacoes(limit=50000)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MovimentaÃ§Ãµes"
    ws.append(["Data/Hora","Tipo","PeÃ§a","CÃ³digo","Qtd","Qtd Ant","Qtd Pos",
                "O.S.","Equipamento","UsuÃ¡rio","Motivo"])
    for r in rows:
        ws.append([r["data_hora"],r["tipo"],r["peca_nome"],r["peca_codigo"],
                   r["quantidade"],r["quantidade_ant"],r["quantidade_pos"],
                   r["os_numero"],r["equipamento_tag"],r["usuario_nome"],r["motivo"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f"movimentacoes_{datetime.now().strftime('%Y%m%d')}.xlsx")

@app.route('/relatorios/criticos-excel')
@login_required
def rel_criticos():
    import openpyxl
    rows = db.listar_pecas(apenas_criticos=True)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "CrÃ­ticos"
    ws.append(["CÃ³digo","Nome","Categoria","Qtd Atual","Qtd MÃ­nima","LocalizaÃ§Ã£o","Fornecedor"])
    for r in rows:
        ws.append([r["codigo"],r["nome"],r["categoria_nome"],
                   r["quantidade"],r["estoque_minimo"],
                   r["localizacao_nome"],r["fornecedor_nome"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f"criticos_{datetime.now().strftime('%Y%m%d')}.xlsx")

# ââ ROTAS: Equipamentos âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/equipamentos')
@login_required
def equipamentos():
    return render_template('equipamentos.html',
        equipamentos=[dict(e) for e in db.listar_equipamentos()])

@app.route('/equipamentos/novo', methods=['POST'])
@login_required
def equipamento_novo():
    f = request.form
    if not f.get('tag') or not f.get('nome'):
        flash('TAG e Nome sÃ£o obrigatÃ³rios.', 'error')
    else:
        db.inserir_equipamento(f['tag'].strip().upper(), f['nome'].strip(),
                               f.get('setor',''), f.get('modelo',''), f.get('fabricante',''))
        flash('Equipamento cadastrado!', 'success')
    return redirect(url_for('equipamentos'))

# ââ ROTAS: Fornecedores âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/fornecedores')
@login_required
def fornecedores():
    return render_template('fornecedores.html',
        fornecedores=[dict(f) for f in db.listar_fornecedores()])

@app.route('/fornecedores/novo', methods=['POST'])
@login_required
def fornecedor_novo():
    f = request.form
    if not f.get('nome'):
        flash('Nome Ã© obrigatÃ³rio.', 'error')
    else:
        db.inserir_fornecedor({'nome':f['nome'],'cnpj':f.get('cnpj',''),
                               'telefone':f.get('telefone',''),
                               'email':f.get('email',''),'contato':f.get('contato','')})
        flash('Fornecedor cadastrado!', 'success')
    return redirect(url_for('fornecedores'))

# ââ ROTAS: UsuÃ¡rios âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/usuarios')
@admin_required
def usuarios():
    return render_template('usuarios.html',
        usuarios=[dict(u) for u in db.listar_usuarios()])

@app.route('/usuarios/novo', methods=['POST'])
@admin_required
def usuario_novo():
    f = request.form
    if not f.get('nome') or not f.get('login') or not f.get('senha'):
        flash('Nome, Login e Senha sÃ£o obrigatÃ³rios.', 'error')
    else:
        db.inserir_usuario(f['nome'], f['login'], f['senha'], f.get('perfil','tecnico'))
        flash(f"UsuÃ¡rio '{f['nome']}' criado!", 'success')
    return redirect(url_for('usuarios'))

# ââ API: busca por barcode (JSON) âââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/api/barcode/<codigo>')
@login_required
def api_barcode(codigo):
    p = db.buscar_peca_barcode(codigo)
    if p: return jsonify(dict(p))
    return jsonify({'error': 'NÃ£o encontrada'}), 404

# ââ MAIN ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
if __name__ == '__main__':
    db.inicializar_banco()
    port = int(os.environ.get('PORT', 5000))
    print(f"\nâ Sistema iniciado em http://localhost:{port}")
    print("   Login: admin / admin123\n")
    app.run(debug=True, host='0.0.0.0', port=port)
