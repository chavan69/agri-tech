-- ===========================================================================
-- Demo data (only inserted when the tables are empty)
-- ===========================================================================

insert into public.market_listings
    (name, category, mode, price, current_bid, quantity, seller, phone, location, image)
select seed.*
from (
    values
        ('Organic Roma Tomatoes', 'Vegetables', 'auction', 28.00, 32.00, '450 kg',
         'Ramesh Gowda', '+91 98450 11223', 'Mandya',
         'https://images.unsplash.com/photo-1592924357228-91a4daadcfea?auto=format&fit=crop&w=600&q=80'),
        ('Premium Sona Masoori Rice', 'Grains', 'direct', 54.00, null, '1,200 kg',
         'Basavaraj Patil', '+91 97312 44556', 'Raichur',
         'https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80')
) as seed (name, category, mode, price, current_bid, quantity, seller, phone, location, image)
where not exists (select 1 from public.market_listings);

insert into public.machinery_listings
    (title, type, category, rate, owner, phone, location, specs)
select seed.*
from (
    values
        ('Mahindra 575 DI Tractor + Rotavator', 'available', 'Heavy Machinery', '₹850 / hour',
         'Suresh Tractor', '+91 98801 33445', 'Hubballi', '45 HP with experienced driver'),
        ('5HP Solar Water Pump & Panel Kit', 'available', 'Smart Equipment', '₹450 / day',
         'GreenSun', '+91 96112 55667', 'Belagavi', 'Portable solar panels included')
) as seed (title, type, category, rate, owner, phone, location, specs)
where not exists (select 1 from public.machinery_listings);
