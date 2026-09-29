import { useState } from "react";
import { submitRefund } from "../api";
import { APPROVAL_THRESHOLD } from "../config";

export function RefundForm({ orderId }: { orderId: string }) {
  const [amount, setAmount] = useState(0);
  const onSubmit = () => submitRefund(orderId, amount);
  return (
    <form>
      <input type="number" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
      {amount > APPROVAL_THRESHOLD && <p>This refund needs approval.</p>}
      <button onClick={onSubmit}>Request refund</button>
    </form>
  );
}
