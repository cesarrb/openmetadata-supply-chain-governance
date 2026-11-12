select
    lifnr as vendor_id,
    name1 as vendor_name,
    land1 as country_code,
    ort01 as city
from {{ source('sap_erp', 'lfa1') }}
