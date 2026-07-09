/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { BarChart } from "./chart_renderer";

const DATE_OPTIONS = [
    { value: "delivery",  label: _t("Delivery Date") },
    { value: "effective", label: _t("Effective Date") },
    { value: "scheduled", label: _t("Scheduled Date") },
];

// Quick-presets keep the planner one click away from the views they
// actually open most days.
const RANGE_PRESETS = [
    { id: "today",    label: _t("Today")         },
    { id: "this_wk",  label: _t("This Week")     },
    { id: "this_mo",  label: _t("This Month")    },
    { id: "last_7",   label: _t("Last 7 Days")   },
    { id: "last_30",  label: _t("Last 30 Days")  },
    { id: "next_30",  label: _t("Next 30 Days")  },
    { id: "ytd",      label: _t("Year to Date")  },
];

// Deterministic colour per channel name so the table, KPIs and chart
// all agree visually.
const CHANNEL_COLORS = {
    "Shopify UK":     "#0a6cff",
    "Shopify US":     "#e63946",
    "Shopify EU":     "#2a9d8f",
    "Direct / Other": "#8d8d8d",
    "Transfers":      "#b27300",
};

function fmtDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const da = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${da}`;
}

function presetRange(id) {
    const today = new Date();
    const start = new Date(today);
    const end = new Date(today);
    if (id === "today") {
        // both = today
    } else if (id === "this_wk") {
        const day = (today.getDay() + 6) % 7; // Monday=0
        start.setDate(today.getDate() - day);
        end.setDate(start.getDate() + 6);
    } else if (id === "this_mo") {
        start.setDate(1);
        end.setMonth(start.getMonth() + 1, 0);
    } else if (id === "last_7") {
        start.setDate(today.getDate() - 6);
    } else if (id === "last_30") {
        start.setDate(today.getDate() - 29);
    } else if (id === "next_30") {
        end.setDate(today.getDate() + 30);
    } else if (id === "ytd") {
        start.setMonth(0, 1);
    }
    return { date_from: fmtDate(start), date_to: fmtDate(end) };
}

export class ProductionDashboard extends Component {
    static template = "hdk_production_dashboard.Dashboard";
    static components = { BarChart };
    static props = ["*"];

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        const init = presetRange("this_mo");
        this.state = useState({
            loading: true,
            refreshing: false,
            date_type: "delivery",
            date_from: init.date_from,
            date_to: init.date_to,
            preset: "this_mo",
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
            this.state.data = await this.rpc(
                "/hdk_production_dashboard/data",
                {
                    date_type: this.state.date_type,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                },
            );
        } catch (err) {
            this.state.error = err.message || String(err);
        } finally {
            this.state.loading = false;
        }
    }

    async onRefreshCache() {
        this.state.refreshing = true;
        try {
            await this.rpc("/hdk_production_dashboard/refresh", {});
            this.notification.add(_t("BOM time cache refreshed."), { type: "success" });
            await this.load();
        } catch (err) {
            this.notification.add(err.message || String(err), { type: "danger" });
        } finally {
            this.state.refreshing = false;
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
            const act = await this.rpc(
                "/hdk_production_dashboard/drilldown",
                {
                    channel_key: channel.key,
                    date_type: this.state.date_type,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    instance_id: channel.instance_id,
                },
            );
            await this.action.doAction(act);
        } catch (err) {
            this.notification.add(err.message || String(err), { type: "danger" });
        }
    }

    colorFor(name) {
        return CHANNEL_COLORS[name] || "#6c757d";
    }

    fmtMoney(value, symbol, position) {
        // symbol/position optional — fall back to company currency when the
        // caller doesn't hand a per-row currency (e.g. grand-totals row).
        if (symbol === undefined) {
            const cur = this.state.data && this.state.data.currency;
            symbol = cur ? cur.symbol : "";
            position = cur ? cur.position : "before";
        }
        const num = (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return position === "after" ? `${num} ${symbol}` : `${symbol}${num}`;
    }

    fmtInt(value) {
        return (value || 0).toLocaleString();
    }

    fmtHours(value) {
        return (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    get refreshLabel() {
        const d = this.state.data && this.state.data.last_refresh;
        if (!d) return _t("Never refreshed");
        const dt = new Date(d.replace(" ", "T") + "Z");
        return _t("BOM cache: %s").replace("%s", dt.toLocaleString());
    }

    get bottleneck() {
        const wc = this.state.data && this.state.data.workcenter_load;
        return wc && wc.length ? wc[0] : null;
    }

    get topWorkcenters() {
        const wc = this.state.data && this.state.data.workcenter_load;
        if (!wc || !wc.length) return [];
        const max = wc[0].minutes || 1;
        return wc.map((w) => ({
            ...w,
            pct: Math.round((w.minutes / max) * 100),
        }));
    }
}

registry.category("actions").add("hdk_production_dashboard", ProductionDashboard);
