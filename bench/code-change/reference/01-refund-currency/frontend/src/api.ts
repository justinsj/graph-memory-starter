import { API_BASE } from "./config";

export const REFUNDS_URL = `${API_BASE}/refunds`;

export async function submitRefund(orderId: string, amount: number, currency = "GBP") {
  return fetch(REFUNDS_URL, {
    method: "POST",
    body: JSON.stringify({ order_id: orderId, amount, currency }),
  });
}

export async function getOrder(orderId: string) {
  const res = await fetch(`/api/orders/${orderId}`);
  return res.json();
}

export async function postAction(body: Record<string, unknown>) {
  return fetch(`${API_BASE}/actions`, { method: "POST", body: JSON.stringify(body) });
}

export function cancelOrder(orderId: string) {
  return postAction({ action: "cancel", order_id: orderId });
}

export function refundViaActions(orderId: string, amount: number, currency = "GBP") {
  return postAction({ action: "refund", order_id: orderId, amount, currency });
}

export async function bulkCancel(orderIds: string[]) {
  return fetch(`${API_BASE}/bulk`, {
    method: "POST",
    body: JSON.stringify({ action: "cancel", order_ids: orderIds }),
  });
}
