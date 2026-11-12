-- OTIF (On Time In Full) at sales-order-line level.
-- On time  = goods issue on or before the customer requested delivery date.
-- In full  = delivered quantity >= ordered quantity.
-- Only standard orders (OR) that have been delivered are measured.
with deliveries as (
    select sales_order_id, sales_order_item,
           max(actual_goods_issue_date) as actual_goods_issue_date,
           sum(delivered_qty)           as delivered_qty
    from {{ ref('stg_delivery_line') }}
    group by 1, 2
)
select
    so.sales_order_id,
    so.sales_order_item,
    so.customer_id,
    c.customer_abc_class,
    so.plant_id,
    so.material_id,
    so.order_date,
    so.requested_delivery_date,
    d.actual_goods_issue_date,
    date_trunc('month', so.requested_delivery_date)::date       as measure_month,
    so.ordered_qty,
    d.delivered_qty,
    (d.actual_goods_issue_date <= so.requested_delivery_date)   as is_on_time,
    (d.delivered_qty >= so.ordered_qty)                         as is_in_full,
    (d.actual_goods_issue_date <= so.requested_delivery_date
       and d.delivered_qty >= so.ordered_qty)                   as is_otif
from {{ ref('stg_sales_order_line') }} so
join deliveries d using (sales_order_id, sales_order_item)
left join {{ ref('stg_customer') }} c on c.customer_id = so.customer_id
where so.order_type = 'OR'
