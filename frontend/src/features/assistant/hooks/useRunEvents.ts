import { useEffect, useState } from "react";
import api from "@/lib/http";
import type { AgentEvent } from "../api";

/** 按运行隔离游标；补齐分页历史，序号去重，卸载后不再写入状态。 */
export function useRunEvents(runId: string, active: boolean) {
  const [snapshot, setSnapshot] = useState<{
    id: string;
    events: AgentEvent[];
  }>({ id: runId, events: [] });
  useEffect(() => {
    let alive = true;
    let polling = false;
    let sequence = 0;
    setSnapshot({ id: runId, events: [] });
    const read = async () => {
      if (polling) return;
      polling = true;
      try {
        let more = true;
        while (alive && more) {
          const items = (
            await api.get<AgentEvent[]>(`/agent/runs/${runId}/events`, {
              params: { after_seq: sequence },
            })
          ).data;
          if (!alive) return;
          if (items.length) {
            sequence = items[items.length - 1].seq;
            setSnapshot((previous) => {
              const events = previous.id === runId ? previous.events : [];
              const seen = new Set(events.map((e) => e.seq));
              return {
                id: runId,
                events: [...events, ...items.filter((e) => !seen.has(e.seq))],
              };
            });
          }
          more = items.length === 200;
        }
      } finally {
        polling = false;
      }
    };
    void read().catch(() => {});
    const timer = active
      ? window.setInterval(() => void read().catch(() => {}), 1000)
      : undefined;
    return () => {
      alive = false;
      if (timer) window.clearInterval(timer);
    };
  }, [runId, active]);
  return snapshot.id === runId ? snapshot.events : [];
}
