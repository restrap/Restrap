/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { BarChart } from "@hdk_production_dashboard/js/chart_renderer";

const DATE_OPTIONS = [
    { value: "delivery",  label: _t("Delivery Date") },
    { value: "effective", label: _t("Effective Date") },
    { value: "scheduled", label: _t("Scheduled Date") },
];

const RANGE_PRESETS = [
    { id: "today",   label: _t("Today") },
    { id: "this_wk", label: _t("This Week") },
    { id: "this_mo", label: _t("This Month") },
    { id: "last_7",  label: _t("Last 7 Days") },
    { id: "last_30", label: _t("Last 30 Days") },
    { id: "ytd",     label: _t("Year to Date") },
];

const CHANNEL_COLORS = {
    "Shopify UK":     "#0a6cff",
    "Shopify US":     "#e63946",
    "Shopify EU":     "#2a9d8f",
    "Direct / Other": "#8d8d8d",
};

function fmtDate(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function presetRange(id) {
    const today = new Date();
    const start = new Date(today);
    const end = new Date(today);
    if (id === "this_wk") {
        const dow = (today.getDay() + 6) % 7;
        start.setDate(today.getDate() - dow);
        end.setDate(start.getDate() + 6);
    } else if (id === "this_mo") {
        start.setDate(1);
        end.setMonth(start.getMonth() + 1, 0);
    } else if (id === "last_7") {
        start.setDate(today.getDate() - 6);
    } else if (id === "last_30") {
        start.setDate(today.getDate() - 29);
    } else if (id === "ytd") {
        start.setMonth(0, 1);
    }
    return { date_from: fmtDate(start), date_to: fmtDate(end) };
}

export class SalesDashboard extends Component {
    static template = "hdk_sales_dashboard.Dashboard";
    static components = { BarChart };
    static props = ["*"];

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        const init = presetRange("this_mo");
        this.state = useState({
            loading: true,
            date_type: "delivery",
            date_from: init.date_from,
            date_to: init.date_to,
            preset: "this_mo",
            product_sort: "units",   // 'units' | 'revenue'
            data: null,
            error: null,
        });

        this.dateOptions = DATE_OPTIONS;
        this.presets = RANGE_PRESETS;

        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.rpc("/hdk_sales_dashboard/data", {
                date_type: this.state.date_type,
                date_from: this.state.date_from,
                date_to: this.state.date_to,
            });
        } catch (err) {
            this.state.error = err.message || String(err);
        } finally {
            this.state.loading = false;
        }
    }

    onPresetClick(id) {
        const r = presetRange(id);
        this.state.preset = id;
        this.state.date_from = r.date_from;
        this.state.date_to = r.date_to;
        this.load();
    }

    onFilterChange() {
        this.state.preset = null;
        this.load();
    }

    async onChannelClick(channel) {
        try {
            const act = await this.rpc("/hdk_sales_dashboard/drilldown", {
                channel_key: channel.key,
                date_type: this.state.date_type,
                date_from: this.state.date_from,
                date_to: this.state.date_to,
                instance_id: channel.instance_id,
            });
            await this.action.doAction(act);
        } catch (err) {
            this.notification.add(err.message || String(err), { type: "danger" });
        }
    }

    async onSalespersonClick(row) {
        try {
            const act = await this.rpc(
                "/hdk_sales_dashboard/drilldown/salesperson",
                {
                    user_id: row.user_id,
                    date_type: this.state.date_type,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                },
            );
            await this.action.doAction(act);
        } catch (err) {
            this.notification.add(err.message || String(err), { type: "danger" });
        }
    }

    async onProductClick(row) {
        try {
            const act = await this.rpc(
                "/hdk_sales_dashboard/drilldown/product",
                {
                    template_id: row.template_id,
                    date_type: this.state.date_type,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                },
            );
            await this.action.doAction(act);
        } catch (err) {
            this.notification.add(err.message || String(err), { type: "danger" });
        }
    }

    async onCustomerClick(row) {
        try {
            const act = await this.rpc(
                "/hdk_sales_dashboard/drilldown/customer",
                {
                    partner_id: row.partner_id,
                    date_type: this.state.date_type,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                },
            );
            await this.action.doAction(act);
        } catch (err) {
            this.notification.add(err.message || String(err), { type: "danger" });
        }
    }

    exportCsv(section) {
        const params = new URLSearchParams({
            section: section,
            date_type: this.state.date_type,
            date_from: this.state.date_from,
            date_to: this.state.date_to,
        });
        window.location.assign(
            `/hdk_sales_dashboard/export?${params.toString()}`
        );
    }

    colorFor(name) {
        return CHANNEL_COLORS[name] || "#6c757d";
    }

    fmtMoney(value, symbol, position) {
        if (symbol === undefined) {
            const cur = this.state.data && this.state.data.currency;
            symbol = cur ? cur.symbol : "";
            position = cur ? cur.position : "before";
        }
        const num = (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
        return position === "after" ? `${num} ${symbol}` : `${symbol}${num}`;
    }

    fmtInt(value)    { return (value || 0).toLocaleString(); }
    fmtNum(value, d) {
        if (value === null || value === undefined) return "—";
        return (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: d, maximumFractionDigits: d,
        });
    }

    get sortedProducts() {
        const list = (this.state.data && this.state.data.top_products) || [];
        const k = this.state.product_sort;
        return [...list].sort((a, b) => (b[k] || 0) - (a[k] || 0));
    }

    get trendBars() {
        const tr = this.state.data && this.state.data.daily_trend;
        if (!tr) return [];
        return tr.points.map((p) => ({ date: p.date, hours: p.orders }));
    }

    setProductSort(s) {
        this.state.product_sort = s;
    }
}

registry.category("actions").add("hdk_sales_dashboard", SalesDashboard);
