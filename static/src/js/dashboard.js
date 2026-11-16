/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, proxy, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class AllReportsDashboard extends Component {
    static template = "all_reports.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        const today = this._formatDateISO(new Date());

        // OWL 3 in Odoo 20 uses proxy() instead of useState()
        this.state = proxy({
            startDate: today,
            endDate: today,
            datePreset: "today",
            selectedPosConfig: "",
            searchQuery: "",
            activeTab: "dashboard",
            data: {
                pos_configs: [],
                kpis: {
                    total_sales: 0,
                    net_sales: 0,
                    total_tax: 0,
                    total_returns: 0,
                    total_discount: 0,
                    total_sessions: 0,
                    total_orders: 0,
                    avg_order_value: 0,
                    total_cash_diff: 0,
                    total_produced_qty: 0,
                    total_lost_qty: 0,
                    total_lost_value: 0,
                    total_lost_cost: 0,
                },
                payment_summary: [],
                top_products: [],
                sessions: [],
                production: [],
                production_vs_sales: [],
                lost_products: [],
            },
            loading: true,
            sessionsPage: 1,
            sessionsPerPage: 5,
            expandedSessions: {},
        });

        onWillStart(async () => {
            await this.fetchData();
        });
    }

    _formatDateISO(dateObj) {
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    async fetchData() {
        this.state.loading = true;
        this.state.sessionsPage = 1;
        this.state.expandedSessions = {};

        try {
            const posConfigId = this.state.selectedPosConfig
                ? parseInt(this.state.selectedPosConfig, 10)
                : false;
            const result = await this.orm.call(
                "all_reports.dashboard",
                "get_dashboard_data",
                [this.state.startDate, this.state.endDate, posConfigId]
            );
            this.state.data = result;
        } catch (e) {
            console.error("Error fetching dashboard data:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async setDatePreset(preset) {
        const now = new Date();
        let start = new Date(now);
        let end = new Date(now);

        if (preset === "today") {
            // start and end are today
        } else if (preset === "yesterday") {
            start.setDate(now.getDate() - 1);
            end.setDate(now.getDate() - 1);
        } else if (preset === "this_week") {
            const day = now.getDay() || 7; // Monday = 1
            start.setDate(now.getDate() - day + 1);
        } else if (preset === "this_month") {
            start = new Date(now.getFullYear(), now.getMonth(), 1);
        }

        this.state.datePreset = preset;
        this.state.startDate = this._formatDateISO(start);
        this.state.endDate = this._formatDateISO(end);
        await this.fetchData();
    }

    async onStartDateChange(ev) {
        this.state.datePreset = "custom";
        this.state.startDate = ev.target.value;
        if (this.state.endDate < this.state.startDate) {
            this.state.endDate = this.state.startDate;
        }
        await this.fetchData();
    }

    async onEndDateChange(ev) {
        this.state.datePreset = "custom";
        this.state.endDate = ev.target.value;
        if (this.state.startDate > this.state.endDate) {
            this.state.startDate = this.state.endDate;
        }
        await this.fetchData();
    }

    async onPosConfigChange(ev) {
        this.state.selectedPosConfig = ev.target.value;
        await this.fetchData();
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value.toLowerCase();
        this.state.sessionsPage = 1;
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    // Filtered Getters
    get filteredSessions() {
        const q = this.state.searchQuery.trim();
        if (!q) return this.state.data.sessions;
        return this.state.data.sessions.filter(
            (s) =>
                s.name.toLowerCase().includes(q) ||
                s.status.toLowerCase().includes(q)
        );
    }

    get paginatedSessions() {
        const start = (this.state.sessionsPage - 1) * this.state.sessionsPerPage;
        const end = start + this.state.sessionsPerPage;
        return this.filteredSessions.slice(start, end);
    }

    get totalSessionPages() {
        return Math.max(
            1,
            Math.ceil(this.filteredSessions.length / this.state.sessionsPerPage)
        );
    }

    get filteredTopProducts() {
        const q = this.state.searchQuery.trim();
        if (!q) return this.state.data.top_products;
        return this.state.data.top_products.filter(
            (p) =>
                p.product_name.toLowerCase().includes(q) ||
                p.category.toLowerCase().includes(q)
        );
    }

    get filteredProduction() {
        const q = this.state.searchQuery.trim();
        if (!q) return this.state.data.production;
        return this.state.data.production.filter((m) =>
            m.product_name.toLowerCase().includes(q)
        );
    }

    get filteredProductionVsSales() {
        const q = this.state.searchQuery.trim();
        if (!q) return this.state.data.production_vs_sales;
        return this.state.data.production_vs_sales.filter((r) =>
            r.product_name.toLowerCase().includes(q)
        );
    }

    get filteredLostProducts() {
        const q = this.state.searchQuery.trim();
        if (!q) return this.state.data.lost_products;
        return this.state.data.lost_products.filter((m) =>
            m.product_name.toLowerCase().includes(q)
        );
    }

    nextPage() {
        if (this.state.sessionsPage < this.totalSessionPages) {
            this.state.sessionsPage++;
        }
    }

    prevPage() {
        if (this.state.sessionsPage > 1) {
            this.state.sessionsPage--;
        }
    }

    toggleSession(sessionId) {
        if (this.state.expandedSessions[sessionId]) {
            delete this.state.expandedSessions[sessionId];
        } else {
            this.state.expandedSessions[sessionId] = true;
        }
    }

    openSessionForm(sessionId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "pos.session",
            res_id: sessionId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    printReport() {
        window.print();
    }

    exportCSV() {
        let headers = [];
        let rows = [];
        const tab = this.state.activeTab;

        if (tab === "sessions") {
            headers = [
                "Session",
                "Status",
                "Opened",
                "Closed",
                "Orders",
                "Opening Balance (DH)",
                "Closing Balance (DH)",
                "Difference (DH)",
                "Total Sales (DH)",
            ];
            rows = this.filteredSessions.map((s) => [
                s.name,
                s.status,
                s.opened_date,
                s.closed_date,
                s.order_count,
                s.opening_balance.toFixed(2),
                s.closing_balance.toFixed(2),
                s.difference.toFixed(2),
                s.total.toFixed(2),
            ]);
        } else if (tab === "top_products") {
            headers = ["Product", "Category", "Quantity Sold", "Revenue (DH)", "Share (%)"];
            rows = this.filteredTopProducts.map((p) => [
                p.product_name,
                p.category,
                p.qty,
                p.amount.toFixed(2),
                p.share,
            ]);
        } else if (tab === "production") {
            headers = ["Product", "Quantity Produced", "Status"];
            rows = this.filteredProduction.map((m) => [
                m.product_name,
                m.quantity,
                m.status,
            ]);
        } else {
            headers = [
                "Lost Product",
                "Quantity",
                "Cost Value (DH)",
                "Retail Value (DH)",
                "Status",
            ];
            rows = this.filteredLostProducts.map((m) => [
                m.product_name,
                m.quantity,
                m.cost_value.toFixed(2),
                m.total_value.toFixed(2),
                m.status,
            ]);
        }

        const escapeCsv = (val) => `"${String(val ?? "").replace(/"/g, '""')}"`;
        const csvContent =
            "\uFEFF" +
            [headers.map(escapeCsv).join(","), ...rows.map((r) => r.map(escapeCsv).join(","))].join(
                "\n"
            );

        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute(
            "download",
            `all_reports_${tab}_${this.state.startDate}_to_${this.state.endDate}.csv`
        );
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "0.00 DH";
        return (
            Number(amount).toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }) + " DH"
        );
    }

    formatNumber(num) {
        if (num === undefined || num === null) return "0";
        return Number(num).toLocaleString("en-US", {
            maximumFractionDigits: 2,
        });
    }
}

registry.category("actions").add("all_reports.dashboard", AllReportsDashboard);