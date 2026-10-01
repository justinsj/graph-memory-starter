import { useEffect, useState } from "react";
import { cancelOrder, getOrder, holdOrder, refundViaActions } from "../api";

export function OrderPage({ orderId }: { orderId: string }) {
  const [order, setOrder] = useState(null);
  useEffect(() => {
    getOrder(orderId).then(setOrder);
  }, [orderId]);
  return (
    <div>
      <h1>Order {orderId}</h1>
      <button onClick={() => cancelOrder(orderId)}>Cancel order</button>
      <button onClick={() => holdOrder(orderId)}>Hold order</button>
      <button onClick={() => refundViaActions(orderId, 10)}>Quick refund</button>
    </div>
  );
}
