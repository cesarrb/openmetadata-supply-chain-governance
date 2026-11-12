-- Aggregate feeding the "Supply Chain Performance" dashboard.
select
    measure_month,
    plant_id,
    count(*)                                         as order_lines,
    round(avg(case when is_on_time then 1 else 0 end), 4)::double precision as on_time_rate,
    round(avg(case when is_in_full then 1 else 0 end), 4)::double precision as in_full_rate,
    round(avg(case when is_otif then 1 else 0 end), 4)::double precision as otif_rate
from {{ ref('fct_otif') }}
where actual_goods_issue_date is not null
group by 1, 2
