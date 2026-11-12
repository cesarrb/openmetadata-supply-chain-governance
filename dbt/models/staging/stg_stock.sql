select
    matnr as material_id,
    werks as plant_id,
    lgort as storage_location,
    labst as unrestricted_stock_qty
from {{ source('sap_erp', 'mard') }}
