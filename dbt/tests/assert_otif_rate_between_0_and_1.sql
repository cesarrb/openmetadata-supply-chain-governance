-- Singular test: a KPI rate outside [0, 1] means a broken calculation.
select * from {{ ref('rpt_otif_monthly') }}
where otif_rate < 0 or otif_rate > 1
