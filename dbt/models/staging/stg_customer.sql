-- Personal contact data (contact_name, contact_email) is deliberately NOT carried
-- into the analytics layer: data minimisation by design (GDPR / Swiss nFADP).
select
    kunnr     as customer_id,
    name1     as customer_name,
    land1     as country_code,
    ort01     as city,
    abc_class as customer_abc_class
from {{ source('sap_erp', 'kna1') }}
