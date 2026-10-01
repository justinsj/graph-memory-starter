import { useEffect, useState } from "react";
import { getConfig, submitRefund } from "../api";

export function RefundForm({ orderId }: { orderId: string }) {
  const [amount, setAmount] = useState(0);
  const [threshold, setThreshold] = useState<number | null>(null);
  useEffect(() => {
    getConfig().then((config) => setThreshold(config.approval_threshold_gbp));
  }, []);
  const onSubmit = () => submitRefund(orderId, amount);
  return (
    <form>
      <input type="number" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
      {threshold !== null && amount > threshold && <p>This refund needs approval.</p>}
      <button onClick={onSubmit}>Request refund</button>
    </form>
  );
}
