{# Shared column definitions, written once and reused by staging and mart models with doc('...'). #}

{% docs material_id %}
SAP material number (MATNR). Identifies the material across all plants.
{% enddocs %}

{% docs plant_id %}
SAP plant code (WERKS): the factory or warehouse that stocks, ships or receives the material.
{% enddocs %}

{% docs customer_id %}
SAP customer number (KUNNR); refers to `stg_customer`.
{% enddocs %}

{% docs vendor_id %}
SAP vendor number (LIFNR); refers to `stg_vendor`.
{% enddocs %}

{% docs sales_order_id %}
SAP sales order number (VBELN).
{% enddocs %}

{% docs sales_order_item %}
Sales order item number (POSNR). Together with `sales_order_id` it identifies one order line.
{% enddocs %}

{% docs country_code %}
Country key, ISO 3166 alpha-2 (LAND1).
{% enddocs %}

{% docs city %}
City of the business partner's address (ORT01).
{% enddocs %}

{% docs order_type %}
SAP document type: OR standard sales order, RE return (sales); NB standard, UB stock transport (purchasing).
{% enddocs %}

{% docs ordered_qty %}
Ordered quantity in the material's base unit of measure.
{% enddocs %}

{% docs net_price %}
Net price per unit in the document currency, after discounts.
{% enddocs %}

{% docs material_description %}
Short material text (MAKTX).
{% enddocs %}

{% docs material_type %}
SAP material type: ROH raw material, HALB semi-finished, FERT finished good.
{% enddocs %}

{% docs material_group %}
Material group (MATKL), used to group materials for purchasing and reporting.
{% enddocs %}

{% docs base_uom %}
Base unit of measure (MEINS); every quantity of the material is expressed in it.
{% enddocs %}

{% docs is_active %}
True when the material is not flagged for deletion in SAP.
{% enddocs %}

{% docs mrp_controller %}
MRP controller (DISPO): the planner responsible for the material at this plant.
{% enddocs %}

{% docs planned_lead_time_days %}
Planned delivery time in days (PLIFZ), used by MRP to schedule replenishment.
{% enddocs %}

{% docs safety_stock_qty %}
Safety stock in base units (EISBE): the buffer kept against demand and supply variability.
Glossary term: *Safety Stock*.
{% enddocs %}

{% docs standard_price_eur %}
Standard price per base unit in EUR (STPRS), used to value stock.
{% enddocs %}

{% docs customer_abc_class %}
Customer ABC classification: A = most important customers by revenue, C = least.
{% enddocs %}

{% docs plan_month %}
First day of the month the plan or the actuals refer to.
{% enddocs %}

{% docs plan_version %}
Plan version label, e.g. V202604 for the plan of April 2026.
{% enddocs %}

{% docs planned_qty %}
Consensus planned quantity in base units, agreed in the monthly S&OP cycle.
{% enddocs %}

{% docs material_plant_key %}
Surrogate key `material_id|plant_id`. One row per material and plant.
{% enddocs %}
