import os, json, uuid, hmac, io
from pathlib import Path
import pandas as pd
import streamlit as st
import joblib, qrcode
from logic import ANSWERS, GUIDE, normalize, fallback, intent_gemini, event, stats, pending

ROOT=Path(file).resolve().parent
DATA=ROOT
DB=ROOT/'piloto.sqlite3'
st.set_page_config(page_title='Precio Justo Agrícola',page_icon='🍇',layout='wide')

def secret(name,default=''):
 try: return str(st.secrets.get(name,os.getenv(name,default)))
 except Exception: return os.getenv(name,default)

@st.cache_data
def load_data():
 return pd.read_csv(DATA/'predicciones_2025.csv'),json.loads((DATA/'metricas.json').read_text()),json.loads((DATA/'variables.json').read_text())
@st.cache_resource
def load_model(): return joblib.load(DATA/'modelo_precio.joblib')

df,m,vars=load_data()
st.title('🍇 Precio Justo Agrícola')
st.caption('Frutos de Cañete · Grupo 4 · Prototipo académico 2026-II')
page=st.sidebar.radio('Explorar',['Asistente virtual','Pronóstico a 7 días','Dashboard','Panel del equipo','Código QR'])
st.sidebar.caption('Datos agrícolas sintéticos. Atención y pedidos de demostración; no se realizan ventas reales.')
if 'sid' not in st.session_state:
 st.session_state.update(sid=uuid.uuid4().hex,history=[],guide=False,consent=False,withdrawn=False,calls=0)
s=st.session_state
if page=='Asistente virtual':
 st.header('Asistente de la campaña de uvas')
 st.info('Piloto académico. No ingreses nombres, teléfonos, direcciones ni otros datos personales. Las consultas libres se pueden enviar a Gemini para reconocer su intención; las respuestas se basan en información validada. Se registran solo sesiones anónimas, permisos y kilos solicitados de prueba. Escribe SALIR para borrar el registro de esta sesión y retirar el permiso. No hay conexión a WhatsApp ni envíos programados.')
 if not s.history: st.chat_message('assistant').write(ANSWERS['saludo'])
 for role, msg, source in s.history:
  with st.chat_message(role):
   st.write(msg)
   if source: st.caption(source)
 prompt=st.chat_input('Escribe UVA, ACEPTO, SALIR o tu consulta',max_chars=300)
 if prompt:
  t=normalize(prompt); source='Regla de negocio'
  if t=='salir':
   event(DB,s.sid,'salir');s.consent=False;s.guide=False;s.withdrawn=True;s.history=[]
   answer='Permiso retirado. Se eliminó el registro anónimo de esta sesión. Puedes escribir UVA para iniciar de nuevo.'
  elif t=='uva':
   s.guide=True;s.withdrawn=False;event(DB,s.sid,'uva');answer=GUIDE+'\n\n¿Aceptas registrar tu permiso y una solicitud de prueba para el piloto? Escribe ACEPTO o SALIR. En este prototipo no se envían mensajes automáticos.'
  elif t=='acepto':
   if s.guide and not s.withdrawn:
    event(DB,s.sid,'acepto');s.consent=True;answer='Gracias. Registramos tu permiso para el piloto. Puedes solicitar una reserva de prueba o escribir SALIR cuando quieras.'
   else: answer='Primero escribe UVA para recibir la guía y el aviso de permiso.'
  else:
   if not s.withdrawn: event(DB,s.sid,'chat')
   key=secret('GEMINI_API_KEY')
   if key and s.calls<12:
    try:
     s.calls+=1;label=intent_gemini(prompt,key,secret('GEMINI_MODEL','gemini-flash-latest'));source='Intención reconocida por Gemini · respuesta validada'
    except Exception:
     label=fallback(prompt);source='Modo alternativo por reglas · Gemini no disponible'
   else:
    label=fallback(prompt);source='Modo por reglas · sin clave o límite de consultas alcanzado'
   answer=ANSWERS[label]
  s.history.append(('user',prompt,''));s.history.append(('assistant',answer,source));st.rerun()
 if s.consent:
  st.subheader('Solicitud de prueba')
  with st.form('solicitud'):
   kg=st.number_input('Cantidad de uva (kg)',min_value=0.5,max_value=100.0,value=2.0,step=0.5)
   submitted=st.form_submit_button('Registrar solicitud de reserva')
  if submitted: event(DB,s.sid,'reserva',kg);st.success('Solicitud registrada para revisión del equipo. No es un pedido confirmado.')
  if st.button('Solicitar revisión humana'):
   event(DB,s.sid,'humano');st.info('Solicitud de revisión registrada en el panel del equipo. No se envió ningún mensaje externo.')
 else: st.caption('Para registrar una solicitud de prueba, escribe UVA y luego ACEPTO.')
elif page=='Pronóstico a 7 días':
 st.header('Pronóstico de precios agrícolas')
 st.warning('Escenario sintético, no una cotización real ni una predicción validada para el mercado actual.')
 product=st.selectbox('Producto',sorted(df.Producto.unique()))
 region=st.selectbox('Región',sorted(df.loc[df.Producto==product,'Región'].unique()))
 subset=df[(df.Producto==product)&(df['Región']==region)]
 idx=st.selectbox('Escenario de referencia de 2025',subset.index,format_func=lambda i:f"{df.at[i,'Fecha']} · {df.at[i,'Variedad']} · {df.at[i,'Tipo_comprador']}")
 row=df.loc[idx]; cat=vars['categoricas'];num=vars['numericas']; values={}
 with st.expander('Variables del escenario',expanded=True):
  cols=st.columns(3)
  for i,k in enumerate(cat): cols[i%3].caption(k.replace('_',' ')+': '+str(row[k]));values[k]=row[k]
  for i,k in enumerate(num):
   if k=='Mes': values[k]=cols[i%3].number_input('Mes',1,12,int(row[k]),key=f'{idx}-{k}')
   else: values[k]=cols[i%3].number_input(k.replace('_',' '),min_value=0.01 if k=='Precio_actual_S_kg' else 0.0,value=float(row[k]),key=f'{idx}-{k}')
 if st.button('Predecir precio',type='primary'):
  pred=float(load_model().predict(pd.DataFrame([values],columns=cat+num))[0]);current=values['Precio_actual_S_kg'];delta=(pred/current-1)*100
  c1,c2,c3=st.columns(3);c1.metric('Precio actual',f'S/ {current:.2f}/kg');c2.metric('Precio estimado a 7 días',f'S/ {pred:.2f}/kg',f'{delta:+.2f}%');c3.metric('Señal','Vender pronto' if delta< -2 else 'Evaluar esperar' if delta>2 else 'Negociar ofertas')
  st.caption('Regla de ±2 %. Considerar perecibilidad, costos y stock antes de decidir.')
elif page=='Dashboard':
 st.header('Indicadores y resultados')
 a=stats(DB);perm=100*a['permisos']/a['uva'] if a['uva'] else None;conv=100*a['confirmados']/a['permisos'] if a['permisos'] else None
 cols=st.columns(4)
 for c,title,val,target in zip(cols,['MAPE del modelo','Captación con permiso','Conversión de prueba','Sesiones de chat'],[f"{m['mape_pct']:.2f}%",f'{perm:.1f}%' if perm is not None else 'Sin medir',f'{conv:.1f}%' if conv is not None else 'Sin medir',str(a['chats'])],['< 10%','≥ 50%','≥ 15%','40 sesiones']):
  c.metric(title,val);c.caption('Meta '+target)
 st.caption('MAPE calculado sobre 506 registros sintéticos de 2025. El resto corresponde a actividad de prueba registrada en esta instalación; sesiones no equivalen a personas únicas. Confirmaciones son de demostración, no ventas. Los registros pueden perderse al reiniciar el servidor.')
 st.subheader('Uva · precio promedio a 7 días por mes (2025)')
 grapes=df[df.Producto=='Uva'].groupby('Mes')[['Precio_estimado_7d_S_kg','Precio_predicho_7d_S_kg']].mean().rename(columns={'Precio_estimado_7d_S_kg':'Referencia simulada','Precio_predicho_7d_S_kg':'Predicción'})
 st.line_chart(grapes,x_label='Mes',y_label='S/ por kg')
 st.subheader('Señales de venta en 506 registros de evaluación')
 st.bar_chart(pd.Series(m['senales'],name='Registros'),y_label='Registros')
 st.caption(f"MAE S/ {m['mae_s_kg']:.4f}/kg · R² {m['r2']:.4f} · Recall binario {m['recall_pct']:.2f}%. El recall bajo limita las alertas de venta inmediata.")
elif page=='Panel del equipo':
 st.header('Revisión humana · demostración')
 pwd=secret('ADMIN_PASSWORD')
 if not pwd: st.warning('Configura ADMIN_PASSWORD en Secrets para habilitar este panel.')
 else:
  entered=st.text_input('Clave interna',type='password')
  if entered and hmac.compare_digest(entered,pwd):
   rows=pending(DB)
   if not rows: st.info('Sin solicitudes pendientes.')
   for sid,kg,status in rows:
    st.write(f'Sesión {sid[:8]} · {status} · {kg if kg is not None else "—"} kg')
    if status=='pendiente' and st.button('Confirmar pedido de prueba',key=sid): event(DB,sid,'confirmar');st.rerun()
  elif entered: st.error('Clave incorrecta.')
else:
 st.header('QR para el jurado')
 url=st.text_input('URL pública de tu aplicación',value=secret('PUBLIC_URL'),placeholder='https://tu-app.streamlit.app')
 if url.startswith('https://') and '.' in url.split('/')[2]:
  img=qrcode.make(url);b=io.BytesIO();img.save(b,format='PNG');st.image(b.getvalue(),width=240);st.download_button('Descargar QR en PNG',b.getvalue(),'QR_Precio_Justo.png','image/png');st.caption('Abre el QR desde un celular sin iniciar sesión para comprobar el acceso.')
 else: st.info('Pega la URL HTTPS real que obtendrás después de publicar la aplicación.')
