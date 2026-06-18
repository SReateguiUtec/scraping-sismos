import json
import requests
import boto3
import hashlib
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Conexión a DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('SismosIGP')

# Endpoint REST de ArcGIS Server del IGP (capa "Sismos Reportados")
# Esta es la fuente de datos real que alimenta la tabla de la web:
# https://ultimosismo.igp.gob.pe/productos/reportes-sismicos
# El sitio es una SPA Angular: el HTML inicial NO contiene la tabla,
# se renderiza en el navegador consumiendo este mismo endpoint.
URL = (
    "https://ide.igp.gob.pe/arcgis/rest/services/monitoreocensis/"
    "SismosReportados/MapServer/0/query"
)

PARAMS = {
    "where": "1=1",
    "outFields": "*",
    "orderByFields": "fechaevento DESC",
    "resultRecordCount": 10,
    "returnGeometry": "false",
    "f": "json",
}


def _generar_id(attrs: dict) -> str:
    """ID determinista para evitar duplicados al re-ejecutar el scraping."""
    raw = f"{attrs.get('fecha')}{attrs.get('hora')}{attrs.get('lat')}{attrs.get('lon')}"
    return hashlib.md5(raw.encode()).hexdigest()


def _to_decimal(valor, default="0") -> Decimal:
    """
    Convierte un valor a Decimal de forma segura.
    Maneja None, strings vacíos, y valores ya numéricos (ArcGIS
    devuelve floats nativos de JSON, no strings).
    """
    if valor is None or valor == "":
        valor = default
    try:
        # Si ya es float/int, repr() evita problemas de precisión binaria
        if isinstance(valor, float):
            return Decimal(repr(valor))
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def lambda_handler(event, context):
    try:
        response = requests.get(URL, params=PARAMS, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            return {
                "statusCode": 502,
                "body": json.dumps({"error": f"Error de ArcGIS: {data['error']}"}),
            }

        features = data.get("features", [])
        if not features:
            return {
                "statusCode": 200,
                "body": json.dumps({"mensaje": "No se encontraron sismos", "guardados": 0}),
            }

        guardados = 0
        for feature in features[:10]:
            attrs = feature.get("attributes", {})
            logger.info("Atributos crudos del sismo: %s", json.dumps(attrs, default=str))

            item = {
                "id": _generar_id(attrs),
                "fecha": str(attrs.get("fecha", "")),
                "hora": str(attrs.get("hora", "")),
                "magnitud": _to_decimal(attrs.get("magnitud")),
                "profundidad": str(attrs.get("profundidad", "")),
                "referencia": str(attrs.get("ref", "")),
                "departamento": str(attrs.get("departamento", "")),
                "latitud": _to_decimal(attrs.get("lat")),
                "longitud": _to_decimal(attrs.get("lon")),
            }

            table.put_item(Item=item)
            guardados += 1

        return {
            "statusCode": 200,
            "body": json.dumps({
                "mensaje": f"{guardados} últimos sismos procesados en DynamoDB",
                "guardados": guardados,
            }),
        }

    except requests.exceptions.RequestException as req_err:
        return {
            "statusCode": 502,
            "body": json.dumps({"error": f"Error de red al contactar al IGP: {str(req_err)}"}),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Error interno: {str(e)}"}),
        }
