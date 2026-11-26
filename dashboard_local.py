"""Panel protegido para el piloto de WhatsApp en Railway."""
import os
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import pandas as pd
import streamlit as st
from streamlit.components.v1 import declare_component
import joblib
from dotenv import load_dotenv
import hmac
import qrcode
import io
from datetime import datetime, timezone, timedelta
import campana
import comercial
import atencion

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DB = Path(os.environ.get('PILOTO_DB_PATH', str(ROOT / 'piloto.sqlite3'))).resolve()
DATA = ROOT / 'modelo' if (ROOT / 'modelo' / 'metricas.json').is_file() else ROOT
CHAT_URL = 'https://wa.me/15551498874?text=UVA'
st.set_page_config(page_title='Precio Justo Agrícola | Panel en la nube', page_icon='🍇', layout='wide')

# Solo se monta después de autenticar el panel del equipo.
_alert_component = declare_component('pja_avisos', path=str(ROOT / 'alerta_asesor'))

@st.fragment(run_every=5)
def alertas_asesor():
    # Consulta de solo lectura; no genera ni modifica tickets.
    try:
        with closing(sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=3)) as c:
            open_ids = {r[0] for r in c.execute('''SELECT t.sid FROM tickets_pja t
                JOIN sesiones s ON s.id=t.sid JOIN campanas p ON p.sid=t.sid
                WHERE t.estado='abierto' AND s.permiso=1''')}
    except sqlite3.Error:
        st.warning('Alertas: no se pudo consultar la bandeja. Se volverá a intentar.')
        return
    previous = st.session_state.get('pja_alert_previous')
    serial = st.session_state.get('pja_alert_serial', 0)
    if previous is not None:
        serial += len(open_ids - previous)
    st.session_state['pja_alert_previous'] = open_ids
    st.session_state['pja_alert_serial'] = serial
    # El navegador solo recibe contadores, nunca identificadores ni mensajes.
    _alert_component(open_count=len(open_ids), serial=serial, key='pja_avisos_browser', default=None)

@st.cache_data
def load_data():
    df = pd.read_csv(DATA / 'predicciones_2025.csv')
    m = json.loads((DATA / 'metricas.json').read_text(encoding='utf-8'))
    variables = json.loads((DATA / 'variables.json').read_text(encoding='utf-8'))
    return df, m, variables

@st.cache_resource
def load_model():
    return joblib.load(DATA / 'modelo_precio.joblib')

def snapshot():
    # No se crea una base vacía accidentalmente si se ejecuta desde otra carpeta.
    if not DB.is_file():
        return None, []
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=10) as c:
        a = c.execute('''SELECT COUNT(*), COALESCE(SUM(uva),0),
            COALESCE(SUM(permiso),0), COALESCE(SUM(permiso=1 AND estado='confirmado'),0),
            COALESCE(SUM(permiso=1 AND estado='pendiente'),0)
            FROM sesiones WHERE id LIKE 'wa-%' ''').fetchone()
        rows = c.execute('''SELECT id,kilos,estado FROM sesiones WHERE id LIKE 'wa-%'
            AND permiso=1 AND estado IN ('pendiente','confirmado','consulta humana') ORDER BY fecha DESC''').fetchall()
    return dict(zip(['chats','uva','permisos','confirmados','pendientes'],a)), rows

def confirm(sid,price=None,pickup_info=None,expected=None):
    campana.init()
    return campana.confirm(sid,price,pickup_info,expected)

st.title('🍇 Precio Justo Agrícola')
st.caption('Frutos de Cañete · Grupo 4 · Panel en la nube de WhatsApp · Piloto académico')
st.sidebar.info('Panel privado para demostración académica en la nube. No hay ventas reales. No compartir las credenciales ni publicar la base SQLite.')
page = st.sidebar.radio('Módulos',['Dashboard','Panel del equipo','Automatización de campaña','Pronóstico a 7 días','Código QR'])
if page != 'Panel del equipo':
    st.session_state.pop('pja_alert_previous', None)
    st.session_state.pop('pja_alert_serial', None)
try:
    df,m,variables = load_data()
except (OSError, ValueError) as e:
    st.error('No se encuentran los resultados del modelo. Guarda este archivo junto a webhook.py, con los archivos de modelo originales.')
    st.stop()

if page in ('Dashboard','Panel del equipo'):
    st.button('Actualizar registros', key='refresh')
    try:
        a,rows = snapshot()
    except sqlite3.Error:
        st.error('No fue posible leer la base local. Comprueba que webhook.py utiliza piloto.sqlite3 y vuelve a actualizar.')
        st.stop()
    if a is None:
        st.warning('Todavía no existe la base de datos. Comprueba el volumen y el servicio webhook.')
        a = dict.fromkeys(['chats','uva','permisos','confirmados','pendientes'],0)

if page=='Dashboard':
    st.header('Indicadores de desempeño')
    perm = 100*a['permisos']/a['uva'] if a['uva'] else None
    conv = 100*a['confirmados']/a['permisos'] if a['permisos'] else None
    for col,title,val,meta,detail in zip(st.columns(4),
        ['MAPE del modelo','Captación con permiso','Conversión de prueba','Contactos de WhatsApp'],
        [f"{m['mape_pct']:.2f}%",f'{perm:.1f}%' if perm is not None else 'Sin medir',f'{conv:.1f}%' if conv is not None else 'Sin medir',str(a['chats'])],
        ['< 10% (propuesta)','≥ 50%','≥ 15%','40 contactos'],
        ['506 registros sintéticos de 2025',f"{a['permisos']} de {a['uva']} contactos con guía",f"{a['confirmados']} de {a['permisos']} contactos con permiso",'Identificadores únicos conservados']):
        col.metric(title,val);col.caption('Meta '+meta);col.caption(detail)
    st.info(f"Solicitudes pendientes: {a['pendientes']} · Confirmadas de prueba: {a['confirmados']}. No son ventas. Las tasas son una fotografía de los registros conservados; SALIR elimina el registro local.")
    st.divider()
    left,right=st.columns(2)
    with left:
        st.subheader('Uva · precio medio a siete días')
        grapes=df[df.Producto=='Uva'].groupby('Mes')[['Precio_estimado_7d_S_kg','Precio_predicho_7d_S_kg']].mean().rename(columns={'Precio_estimado_7d_S_kg':'Referencia simulada','Precio_predicho_7d_S_kg':'Predicción'})
        st.line_chart(grapes,x_label='Mes de 2025',y_label='S/ por kg')
        st.caption('Comparación entre pronóstico y referencia sintética, no precios reales.')
    with right:
        st.subheader('Señales de venta del modelo')
        st.bar_chart(pd.Series(m['senales'],name='Registros'),y_label='Registros')
        st.caption('506 registros de evaluación, todos los productos; umbral de ±2 %.')
    st.caption(f"MAE S/ {m['mae_s_kg']:.4f}/kg · R² {m['r2']:.4f} · Recall binario {m['recall_pct']:.2f}%. El recall bajo limita las alertas de venta inmediata.")

elif page=='Panel del equipo':
    st.header('Centro de atención comercial')
    pwd=os.getenv('ADMIN_PASSWORD','')
    entered=st.text_input('Contraseña interna',type='password')
    if not pwd or not entered or not hmac.compare_digest(entered,pwd):
        st.session_state.pop('pja_alert_previous', None)
        st.session_state.pop('pja_alert_serial', None)
        if entered: st.error('Contraseña incorrecta o no configurada.')
        st.stop()
    campana.init()
    alertas_asesor()
    tickets=atencion.tickets()
    with campana.conn() as c:
        orders=[dict(r) for r in c.execute("SELECT id,kilos,estado FROM sesiones WHERE permiso=1 AND id LIKE 'wa-%' AND estado IN ('pendiente','confirmado','rechazado') ORDER BY fecha DESC")]
    pending=sum(r['estado']=='pendiente' for r in orders)
    opened=sum(t['estado']=='abierto' for t in tickets)
    for col,label,value in zip(st.columns(4),['Consultas abiertas','Reservas pendientes','Confirmadas','Rechazadas'],[opened,pending,sum(r['estado']=='confirmado' for r in orders),sum(r['estado']=='rechazado' for r in orders)]):col.metric(label,value)
    st.caption('Catálogo e inventario de referencia. Sin ventas ni cobros reales. Los números de teléfono no se muestran.')
    def notice():
        flash=st.session_state.pop('panel_flash',None)
        if flash: st.success(flash)
    def saved(ok,msg):
        if ok:
            st.session_state['panel_flash']=msg;st.rerun()
        else:st.warning(msg if msg.startswith(('No','Es','Ventana','Solo','El stock','Valores','Indica','Hay')) else 'No se pudo completar la operación. Actualiza registros y revisa el estado.')
    notice()
    section=st.radio('Gestión',['Bandeja de atención','Reservas','Catálogo e inventario'],horizontal=True,key='gestion')
    if section=='Bandeja de atención':
        st.subheader('Bandeja de consultas humanas')
        st.caption('Gemini deriva solo las excepciones. Mientras la consulta está abierta, los mensajes del cliente llegan a esta bandeja. Al cerrarla, Gemini vuelve a atender.')
        filter_=st.radio('Estado',['Abiertas','Cerradas','Todas'],horizontal=True)
        visible=[t for t in tickets if filter_=='Todas' or (filter_=='Abiertas' and t['estado']=='abierto') or (filter_=='Cerradas' and t['estado']=='cerrado')]
        if not visible:st.info('No hay consultas en esta vista.')
        else:
            selected=st.selectbox('Seleccionar consulta',visible,format_func=lambda t:'Contacto …'+t['sid'][-8:]+' · '+t['estado'])
            sid=selected['sid'];opened=selected['estado']=='abierto'
            if not atencion.messages(sid):st.info('Derivación anterior a la nueva bandeja. No se conserva el mensaje original.')
            for msg in atencion.messages(sid):
                with st.chat_message('user' if msg['rol']=='cliente' else 'assistant'):
                    st.caption(('Cliente' if msg['rol']=='cliente' else 'Equipo')+' · '+datetime.fromtimestamp(msg['fecha'],timezone(timedelta(hours=-5))).strftime('%d/%m %H:%M'))
                    st.text(msg['texto'])
                    if msg['rol']=='equipo':st.caption('Envío: '+str(msg['envio'] or 'sin registro')+' · '+str(msg['resultado'] or ''))
            if opened:
                window=0<=campana.clock()-selected['ultimo_cliente']<23*3600+55*60
                if not window:st.warning('Ventana de WhatsApp cerrada. Espera un nuevo mensaje del cliente.')
                with st.form('respuesta-'+sid,clear_on_submit=True):
                    answer=st.text_area('Respuesta del equipo',max_chars=1000,placeholder='Escribe una respuesta breve. No incluyas datos sensibles ni solicites pagos.')
                    if st.form_submit_button('Enviar por WhatsApp',type='primary',disabled=not window):saved(*atencion.queue(sid,answer))
                if st.button('Cerrar atención y devolver el control a Gemini',key='close-'+sid):saved(atencion.close(sid),'Atención cerrada. Gemini podrá responder el siguiente mensaje.' if not any(m.get('envio') in ('pendiente','enviando') for m in atencion.messages(sid)) else 'Hay respuestas por enviar. Actualiza los registros antes de cerrar.')
            elif st.button('Reabrir consulta',key='reopen-'+sid):saved(atencion.open_ticket(sid,''),'Consulta reabierta.')
    elif section=='Reservas':
        st.subheader('Gestión de reservas')
        filter_=st.radio('Filtrar',['Todas','Pendientes','Confirmadas','Rechazadas'],horizontal=True)
        mapping={'Pendientes':'pendiente','Confirmadas':'confirmado','Rechazadas':'rechazado'}
        visible=[r for r in orders if filter_=='Todas' or r['estado']==mapping[filter_]]
        if not visible:st.info('No hay reservas en esta vista.')
        cr=campana.report()
        for r in visible:
            sid,kg,status=r['id'],r['kilos'],r['estado'];q=comercial.detalle(sid)
            with st.container(border=True):
                st.subheader('Contacto …'+sid[-8:]);st.caption(status.capitalize())
                if q:
                    a1,a2,a3=st.columns(3);a1.metric(comercial.CATALOGO[q['variedad']]['nombre'],f"{q['kg']:g} kg");a2.metric('Precio por kg',f"S/ {q['precio']:.2f}");a3.metric('Total referencial',f"S/ {q['total']:.2f}")
                elif kg is not None:st.write(f'{kg:g} kg · Registro anterior sin cotización')
                if status=='pendiente':
                    with st.form('revision-'+sid):
                        price=st.number_input('Precio de referencia por kg (S/)',min_value=0.0,value=float(q['precio']) if q else 0.0,step=0.1,disabled=bool(q))
                        pickup_info=st.text_input('Lugar, fecha y horario referencial',value=comercial.RECOJO if q else '',max_chars=200)
                        stock=st.checkbox('Verifiqué las condiciones de referencia')
                        if st.form_submit_button('Confirmar reserva',type='primary'):
                            if not stock or price<=0 or not pickup_info.strip():st.warning('Completa y revisa las condiciones.')
                            else:saved(confirm(sid,price,pickup_info,q),'Reserva confirmada y aviso encolado (si tiene campaña activa).')
                    with st.expander('Rechazar o solicitar una nueva cotización'):
                        with st.form('reject-'+sid):
                            reason=st.text_area('Motivo para el cliente',max_chars=300,placeholder='Ej. Es necesario ajustar la cantidad. Solicita una nueva cotización.')
                            ack=st.checkbox('Liberar el stock y avisar al cliente')
                            if st.form_submit_button('Rechazar reserva'):
                                if ack:saved(*atencion.reject(sid,reason))
                                else:st.warning('Confirma la liberación de stock.')
                elif status=='confirmado':
                    own=[x for x in cr if x['sid']==sid]
                    if not own:st.caption('Registro anterior sin nueva autorización de campaña.')
                    elif own[0]['recojo'] is not None:st.caption('Recojo simulado registrado · Encuesta: '+str(own[0]['encuesta'] or 'pendiente'))
                    else:
                        notification=next((x for x in own if x['tipo']=='confirmacion'),None)
                        if notification:st.caption('Confirmación por WhatsApp: '+str(notification['envio']))
                        if st.button('Registrar recojo y solicitar encuesta',key='pickup-'+sid):saved(campana.pickup(sid),'Recojo simulado registrado y encuesta encolada.')
                if st.button('Abrir atención humana',key='ticket-'+sid):saved(atencion.open_ticket(sid,''),'Consulta abierta. Accede a Bandeja de atención.')
        st.caption('No se modifica unilateralmente una cotización aceptada. Para cambios de una reserva pendiente, rechaza con motivo y solicita una nueva cotización al cliente.')
    else:
        st.subheader('Catálogo e inventario')
        st.info('Valores simulados para cotizaciones del asistente. Stock total incluye las cantidades ya apartadas. Las reservas existentes conservan el precio acordado.')
        catalog=comercial.catalogo('')['variedades']
        for item in catalog:
            k=item['id']
            with st.container(border=True):
                st.subheader(item['nombre'])
                a1,a2,a3=st.columns(3);a1.metric('Stock total',f"{item['stock_kg']:g} kg");a2.metric('Apartado',f"{item['stock_kg']-item['disponible_kg']:g} kg");a3.metric('Disponible',f"{item['disponible_kg']:g} kg")
                with st.form('catalog-'+k):
                    price=st.number_input('Precio por kg (S/)',min_value=0.01,max_value=10000.0,value=float(item['precio_kg']),step=0.1,format='%.2f')
                    stock=st.number_input('Stock total de referencia (kg)',min_value=0.0,max_value=100000.0,value=float(item['stock_kg']),step=1.0,format='%.3f')
                    if st.form_submit_button('Guardar cambios',type='primary'):saved(*comercial.update_product(k,price,stock))
        st.caption('Jabas de 10 kg y descuento del 8 % desde 50 jabas; se mantienen las reglas del catálogo anterior.')

elif page=='Automatización de campaña':
    st.header('Workflow de seguimiento autorizado')
    pwd=os.getenv('ADMIN_PASSWORD','')
    entered=st.text_input('Contraseña interna',type='password',key='campaign_password')
    if not pwd or not entered or not hmac.compare_digest(entered,pwd):
        if entered: st.error('Contraseña incorrecta o no configurada.')
        st.stop()
    st.button('Actualizar seguimiento')
    campana.init(); records=campana.report()
    st.info('Modo demo: días 1, 3 y 7 = 0, 1 y 2 min. Cierre 2 min después de la oferta. Modo real: 0, 2 y 6 días; cierre 48 h después de la oferta. Son pruebas académicas, no ventas.')
    if not records: st.info('Todavía no hay contactos con el nuevo consentimiento. Escribe UVA y luego ACEPTO en WhatsApp.')
    else:
        contacts={r['sid']:r for r in records}
        def local(t): return datetime.fromtimestamp(t,timezone(timedelta(hours=-5))).strftime('%d/%m %H:%M:%S') if t else '—'
        cols=st.columns(4)
        for c,label,value in zip(cols,['Campañas autorizadas','Activas','Cerradas sin confirmación','Encuestas respondidas'],[len(contacts),sum(r['estado']=='activa' for r in contacts.values()),sum(r['estado']=='cerrada' for r in contacts.values()),sum(r['encuesta'] is not None for r in contacts.values())]): c.metric(label,value)
        st.dataframe(pd.DataFrame([{'Contacto':'…'+r['sid'][-8:],'Modo':r['modo'],'Variante':r['variante'],'Campaña':r['estado'],'Etapa':r['tipo'],'Fecha permiso':local(r['permiso_fecha']),'Programado':local(r['vence']),'Estado del envío':r['envio'],'Resultado':r['resultado'],'Enviado':local(r['enviado']),'Cierre previsto':local(r['cierre'])} for r in records]),hide_index=True,use_container_width=True)
        st.caption('Aceptado = Meta recibió la petición; entregado/leído = evento posterior de Meta. Los estados inciertos no se reenvían automáticamente. SALIR elimina también estos datos.')
        st.subheader('Prueba A/B · oferta del día 7')
        ab=[]
        for variant in ('A','B'):
            for m in ('demo','real'):
                eligible=[r for r in records if r['tipo']=='d7'+variant.lower() and r['modo']==m and r['envio'] in ('entregado','leido')]
                n=len(eligible); converted=sum(r['conversion_fecha'] is not None and r['enviado'] is not None and r['conversion_fecha']>=r['enviado'] for r in eligible)
                ab.append({'Modo':m,'Variante':variant,'Ofertas con entrega comprobada':n,'Confirmaciones posteriores':converted,'Tasa descriptiva':f'{converted/n:.1%}' if n else 'Sin medir'})
        st.dataframe(pd.DataFrame(ab),hide_index=True,use_container_width=True)
        st.caption('Asignación estable por seudónimo. No se determina ganador con una muestra insuficiente; se excluyen confirmaciones previas a la oferta. No mide efecto causal.')


elif page=='Pronóstico a 7 días':
    st.header('Pronóstico de precios agrícolas')
    st.warning('Escenario sintético de referencia, no cotización del mercado actual.')
    p=st.selectbox('Producto',sorted(df.Producto.unique()))
    r=st.selectbox('Región',sorted(df.loc[df.Producto==p,'Región'].unique()))
    subset=df[(df.Producto==p)&(df['Región']==r)]
    idx=st.selectbox('Escenario de 2025',subset.index,format_func=lambda i:f"{df.at[i,'Fecha']} · {df.at[i,'Variedad']} · {df.at[i,'Tipo_comprador']}")
    row=df.loc[idx];cat=variables['categoricas'];num=variables['numericas'];values={}
    with st.expander('Variables del escenario',expanded=True):
        cols=st.columns(3)
        for i,k in enumerate(cat):
            cols[i%3].caption(k.replace('_',' ')+': '+str(row[k]));values[k]=row[k]
        for i,k in enumerate(num):
            if k=='Mes': values[k]=cols[i%3].number_input('Mes',1,12,int(row[k]),key=f'{idx}-{k}')
            else: values[k]=cols[i%3].number_input(k.replace('_',' '),min_value=0.01 if k=='Precio_actual_S_kg' else 0.0,value=float(row[k]),key=f'{idx}-{k}')
    if st.button('Predecir precio',type='primary'):
        pred=float(load_model().predict(pd.DataFrame([values],columns=cat+num))[0]);current=values['Precio_actual_S_kg'];delta=(pred/current-1)*100
        c1,c2,c3=st.columns(3);c1.metric('Precio actual',f'S/ {current:.2f}/kg');c2.metric('Precio estimado a 7 días',f'S/ {pred:.2f}/kg',f'{delta:+.2f}%');c3.metric('Señal','Vender pronto' if delta< -2 else 'Evaluar esperar' if delta>2 else 'Negociar ofertas')
        st.caption('Regla de ±2 %. Considerar perecibilidad, costos y stock antes de decidir.')

else:
    st.header('QR de WhatsApp · piloto')
    b=io.BytesIO();qrcode.make(CHAT_URL).save(b,format='PNG');st.image(b.getvalue(),width=260)
    st.download_button('Descargar QR de WhatsApp',b.getvalue(),'QR_WhatsApp_Precio_Justo.png','image/png')
    st.markdown(f'[Abrir chat de WhatsApp]({CHAT_URL})')
    st.warning('El número de prueba de Meta solo atiende a destinatarios autorizados. Verifica el QR desde un celular registrado. El servicio Railway y el token de Meta deben estar activos.')
