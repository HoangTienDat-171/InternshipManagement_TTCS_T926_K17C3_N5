export function signalDashboardMetricsChanged() {
  window.dispatchEvent(new Event('ims-dashboard-metrics-updated'));
}
