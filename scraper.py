import json
import requests
from bs4 import BeautifulSoup
import boto3
import uuid

# Conexión a DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('SismosIGP')

def lambda_handler(event, context):
    url = "https://ultimosismo.igp.gob.pe/productos/reportes-sismicos"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # OJO: Deberás inspeccionar el HTML del IGP para ajustar este selector
        # Aquí asumo que cada sismo está en una fila <tr> de una tabla
        filas_sismos = soup.select('table tbody tr')[:10]
        
        for fila in filas_sismos:
            columnas = fila.find_all('td')
            if len(columnas) >= 4:
                item = {
                    'id': str(uuid.uuid4()),
                    'fecha': columnas[0].text.strip(),
                    'magnitud': columnas[1].text.strip(),
                    'profundidad': columnas[2].text.strip(),
                    'referencia': columnas[3].text.strip()
                }
                table.put_item(Item=item)
                
        return {
            'statusCode': 200,
            'body': json.dumps({'mensaje': '10 últimos sismos procesados en DynamoDB'})
        }
        
    except requests.exceptions.RequestException as req_err:
        return {
            'statusCode': 502,
            'body': json.dumps({'error': f'Error de red al contactar al IGP: {str(req_err)}'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Error interno: {str(e)}'})
        }
