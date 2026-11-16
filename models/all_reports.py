from datetime import datetime, time
from zoneinfo import ZoneInfo
import logging

from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class AllReportsDashboard(models.TransientModel):
    _name = 'all_reports.dashboard'
    _description = 'All Reports Dashboard Logic'

    @api.model
    def get_dashboard_data(self, start_date_str, end_date_str, pos_config_id=False):
        _logger.info(
            "AllReportsDashboard: get_dashboard_data called with %s to %s (pos_config_id=%s)",
            start_date_str, end_date_str, pos_config_id
        )
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            # Odoo 20 uses zoneinfo.ZoneInfo via self.env.tz
            user_tz = self.env.tz or ZoneInfo(self.env.user.tz or 'UTC')
            if isinstance(user_tz, str):
                user_tz = ZoneInfo(user_tz)
            utc_tz = ZoneInfo('UTC')

            start_of_range_user = datetime.combine(start_date, time.min, tzinfo=user_tz)
            end_of_range_user = datetime.combine(end_date, time.max, tzinfo=user_tz)

            start_of_day_utc = start_of_range_user.astimezone(utc_tz).replace(tzinfo=None)
            end_of_day_utc = end_of_range_user.astimezone(utc_tz).replace(tzinfo=None)

            def _fmt_dt(dt_val):
                if not dt_val:
                    return False
                aware_utc = dt_val.replace(tzinfo=utc_tz)
                return aware_utc.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')

            # Available POS Configurations for the filter dropdown
            pos_configs = self.env['pos.config'].sudo().search_read([], ['id', 'name'])

            # 1. POS Sessions
            today = fields.Date.context_today(self)
            today_in_range = (start_date <= today <= end_date)

            closed_domain = [
                ('stop_at', '>=', start_of_day_utc),
                ('stop_at', '<=', end_of_day_utc),
            ]
            open_domain = [('stop_at', '=', False)]

            if pos_config_id:
                config_id_int = int(pos_config_id)
                closed_domain.append(('config_id', '=', config_id_int))
                open_domain.append(('config_id', '=', config_id_int))

            sessions = self.env['pos.session'].sudo().search(closed_domain, order='start_at desc')
            if today_in_range:
                open_sessions = self.env['pos.session'].sudo().search(open_domain, order='start_at desc')
                sessions = open_sessions | sessions

            sessions_data = []
            sales_agg = {}
            global_products_agg = {}
            global_payments_agg = {}

            total_gross_sales = 0.0
            total_tax = 0.0
            total_returns = 0.0
            total_discount = 0.0
            total_orders_count = 0
            total_cash_diff = 0.0

            BomModel = self.env['mrp.bom'].sudo()

            for session in sessions:
                try:
                    # Exclude cancelled and draft orders
                    orders = session.order_ids.filtered(lambda o: o.state not in ('draft', 'cancel'))
                    order_count = len(orders)
                    category_data = {}
                    session_payments = {}

                    # Aggregate payments per session and globally
                    for payment in orders.mapped('payment_ids'):
                        pm_name = payment.payment_method_id.name or 'Other'
                        session_payments[pm_name] = session_payments.get(pm_name, 0.0) + payment.amount
                        global_payments_agg[pm_name] = global_payments_agg.get(pm_name, 0.0) + payment.amount

                    for order in orders:
                        for line in order.lines:
                            product = line.product_id
                            p_display_name = product.display_name

                            # Track product sales for Production vs Sales
                            sales_agg[p_display_name] = sales_agg.get(p_display_name, 0.0) + line.qty

                            # Check for BOM (variant-specific OR template-level)
                            bom = BomModel.search([
                                '|',
                                ('product_id', '=', product.id),
                                '&',
                                ('product_id', '=', False),
                                ('product_tmpl_id', '=', product.product_tmpl_id.id),
                            ], limit=1)
                            if bom and bom.product_qty:
                                factor = line.qty / bom.product_qty
                                for bom_line in bom.bom_line_ids:
                                    comp_name = bom_line.product_id.display_name
                                    comp_qty = bom_line.product_qty * factor
                                    sales_agg[comp_name] = sales_agg.get(comp_name, 0.0) + comp_qty

                            # Determine POS Category
                            cat_name = 'Uncategorized'
                            if 'pos_categ_ids' in product._fields and product.pos_categ_ids:
                                cat_name = product.pos_categ_ids[0].name
                            elif 'pos_categ_id' in product._fields and product.pos_categ_id:
                                cat_name = product.pos_categ_id.name

                            if cat_name not in category_data:
                                category_data[cat_name] = {'name': cat_name, 'products': {}, 'total': 0.0}

                            p_name = product.name
                            if p_name not in category_data[cat_name]['products']:
                                category_data[cat_name]['products'][p_name] = {
                                    'name': p_name,
                                    'qty': 0.0,
                                    'amount': 0.0,
                                }
                            category_data[cat_name]['products'][p_name]['qty'] += line.qty
                            category_data[cat_name]['products'][p_name]['amount'] += line.price_subtotal_incl
                            category_data[cat_name]['total'] += line.price_subtotal_incl

                            # Global Top Products tracking
                            if p_display_name not in global_products_agg:
                                global_products_agg[p_display_name] = {
                                    'product_name': p_display_name,
                                    'category': cat_name,
                                    'qty': 0.0,
                                    'amount': 0.0,
                                }
                            global_products_agg[p_display_name]['qty'] += line.qty
                            global_products_agg[p_display_name]['amount'] += line.price_subtotal_incl

                    breakdown = []
                    for cat in category_data.values():
                        breakdown.append({
                            'name': cat['name'],
                            'total': cat['total'],
                            'products': sorted(
                                list(cat['products'].values()),
                                key=lambda x: x['amount'],
                                reverse=True,
                            ),
                        })
                    breakdown.sort(key=lambda x: x['total'], reverse=True)

                    gross_sales = sum(orders.mapped('amount_total'))
                    tax = sum(orders.mapped('amount_tax'))
                    returns = sum(orders.filtered(lambda o: o.amount_total < 0).mapped('amount_total'))

                    discount = 0.0
                    for order in orders:
                        for line in order.lines:
                            if line.discount:
                                discount += (line.price_unit * line.qty * line.discount / 100.0)

                    opening_balance = getattr(session, 'cash_register_balance_start', 0.0) or 0.0
                    closing_balance = getattr(session, 'cash_register_balance_end_real', 0.0) or 0.0
                    if closing_balance == 0.0:
                        closing_balance = getattr(session, 'cash_register_balance_end', 0.0) or 0.0
                    difference = getattr(session, 'cash_register_difference', 0.0) or 0.0

                    total = getattr(session, 'amount_total_incl', 0.0) or gross_sales

                    # Skip empty opening_control sessions
                    if session.state == 'opening_control' or (total == 0.0 and session.stop_at):
                        continue

                    total_gross_sales += total
                    total_tax += tax
                    total_returns += returns
                    total_discount += discount
                    total_orders_count += order_count
                    total_cash_diff += difference

                    payments_list = [
                        {'name': k, 'amount': v}
                        for k, v in sorted(session_payments.items(), key=lambda x: x[1], reverse=True)
                    ]

                    sessions_data.append({
                        'name': f"{session.config_id.name} - {session.name}",
                        'id': session.id,
                        'config_id': session.config_id.id,
                        'config_name': session.config_id.name,
                        'opened_date': _fmt_dt(session.start_at) or '-',
                        'closed_date': _fmt_dt(session.stop_at) or 'Open',
                        'is_open': not bool(session.stop_at),
                        'status': session.state,
                        'order_count': order_count,
                        'opening_balance': opening_balance,
                        'closing_balance': closing_balance,
                        'difference': difference,
                        'gross_sales': gross_sales,
                        'tax': tax,
                        'returns': returns,
                        'discount': discount,
                        'total': total,
                        'payments': payments_list,
                        'breakdown': breakdown,
                    })
                except Exception as e:
                    _logger.error("Error processing session %s: %s", session.id, e)
                    continue

            # 2. Production Moves
            production_moves = self.env['stock.move'].sudo().search([
                ('state', '=', 'done'),
                ('location_id.usage', '=', 'production'),
                ('location_dest_id.usage', '=', 'internal'),
                ('date', '>=', start_of_day_utc),
                ('date', '<=', end_of_day_utc),
            ])

            production_agg = {}
            total_produced_qty = 0.0
            for move in production_moves:
                name = move.product_id.display_name
                uom_name = move.product_uom.name if 'product_uom' in move._fields else ''
                if name not in production_agg:
                    production_agg[name] = {
                        'quantity': 0.0,
                        'uom': uom_name,
                        'status': move.state,
                    }
                production_agg[name]['quantity'] += move.quantity
                total_produced_qty += move.quantity

            production_data = [
                {
                    'product_name': name,
                    'quantity': data['quantity'],
                    'uom': data['uom'],
                    'status': data['status'].capitalize(),
                }
                for name, data in sorted(production_agg.items(), key=lambda x: x[1]['quantity'], reverse=True)
            ]

            # 3. Production vs Sales Comparison
            production_vs_sales = []
            for name, data in production_agg.items():
                produced = data['quantity']
                sold = sales_agg.get(name, 0.0)
                production_vs_sales.append({
                    'product_name': name,
                    'produced_qty': produced,
                    'sales_qty': sold,
                    'difference': produced - sold,
                })
            production_vs_sales.sort(key=lambda x: x['difference'])

            # 4. Lost & Scrapped Products
            lost_moves = self.env['stock.move'].sudo().search([
                ('state', '=', 'done'),
                ('location_id.usage', '=', 'internal'),
                ('location_dest_id.usage', '=', 'inventory'),
                ('date', '>=', start_of_day_utc),
                ('date', '<=', end_of_day_utc),
            ])

            lost_agg = {}
            total_lost_retail_value = 0.0
            total_lost_cost_value = 0.0
            total_lost_qty = 0.0

            for move in lost_moves:
                product = move.product_id
                name = product.display_name
                if name not in lost_agg:
                    lost_agg[name] = {
                        'quantity': 0.0,
                        'status': move.state,
                        'cost_value': 0.0,
                        'total_value': 0.0,
                        'location': move.location_dest_id.display_name,
                    }
                qty = move.quantity
                retail_val = qty * (product.lst_price or 0.0)
                cost_val = qty * (product.standard_price or 0.0)

                lost_agg[name]['quantity'] += qty
                lost_agg[name]['total_value'] += retail_val
                lost_agg[name]['cost_value'] += cost_val

                total_lost_qty += qty
                total_lost_retail_value += retail_val
                total_lost_cost_value += cost_val

            lost_data = [
                {
                    'product_name': name,
                    'location': data['location'],
                    'quantity': data['quantity'],
                    'status': data['status'].capitalize(),
                    'cost_value': data['cost_value'],
                    'total_value': data['total_value'],
                }
                for name, data in sorted(lost_agg.items(), key=lambda x: x[1]['total_value'], reverse=True)
            ]

            # 5. Top Selling Products & Payment Summary
            top_products = sorted(
                list(global_products_agg.values()),
                key=lambda x: x['amount'],
                reverse=True,
            )
            for prod in top_products:
                prod['share'] = round((prod['amount'] / total_gross_sales * 100.0), 1) if total_gross_sales > 0 else 0.0

            payment_methods_summary = [
                {'name': k, 'amount': v}
                for k, v in sorted(global_payments_agg.items(), key=lambda x: x[1], reverse=True)
            ]

            avg_order_value = (total_gross_sales / total_orders_count) if total_orders_count else 0.0

            return {
                'pos_configs': pos_configs,
                'kpis': {
                    'total_sales': total_gross_sales,
                    'net_sales': total_gross_sales - total_tax,
                    'total_tax': total_tax,
                    'total_returns': total_returns,
                    'total_discount': total_discount,
                    'total_sessions': len(sessions_data),
                    'total_orders': total_orders_count,
                    'avg_order_value': avg_order_value,
                    'total_cash_diff': total_cash_diff,
                    'total_produced_qty': total_produced_qty,
                    'total_lost_qty': total_lost_qty,
                    'total_lost_value': total_lost_retail_value,
                    'total_lost_cost': total_lost_cost_value,
                },
                'payment_summary': payment_methods_summary,
                'top_products': top_products,
                'sessions': sessions_data,
                'production': production_data,
                'production_vs_sales': production_vs_sales,
                'lost_products': lost_data,
            }
        except Exception as e:
            _logger.error("Error in get_dashboard_data: %s", e)
            raise