/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * BarChart — minimal dependency-free SVG bar chart for the daily trend.
 * Props: { points: [{date, hours}], bucket: 'day'|'week'|'month' }
 * Designed so we don't need to ship Chart.js or D3 as an asset.
 */
export class BarChart extends Component {
    static template = "hdk_production_dashboard.BarChart";
    static props = {
        points: { type: Array },
        bucket: { type: String, optional: true },
    };

    get bars() {
        const pts = this.props.points || [];
        if (!pts.length) {
            return [];
        }
        const max = Math.max(...pts.map((p) => p.hours), 1);
        const w = 100 / pts.length;
        return pts.map((p, i) => ({
            x: i * w,
            width: Math.max(w - 1, 0.5),
            height: (p.hours / max) * 90,
            y: 100 - (p.hours / max) * 90,
            label: this.formatBucket(p.date),
            hours: p.hours,
        }));
    }

    formatBucket(iso) {
        const d = new Date(iso);
        const bucket = this.props.bucket || "day";
        if (bucket === "month") {
            return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
        }
        if (bucket === "week") {
            return `W${this.weekNumber(d)}`;
        }
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }

    weekNumber(d) {
        const target = new Date(d.valueOf());
        const dayNr = (d.getDay() + 6) % 7;
        target.setDate(target.getDate() - dayNr + 3);
        const firstThursday = target.valueOf();
        target.setMonth(0, 1);
        if (target.getDay() !== 4) {
            target.setMonth(0, 1 + ((4 - target.getDay()) + 7) % 7);
        }
        return 1 + Math.ceil((firstThursday - target) / 604800000);
    }
}
