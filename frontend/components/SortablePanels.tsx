"use client";

import { closestCenter, DndContext, DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { arrayMove, rectSortingStrategy, SortableContext, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { DragHandle } from "@/components/charts";

export type PanelItem = { id: string; wide?: boolean; node: React.ReactNode };

/**
 * Panels in a two-column grid that can be dragged into any order by the grip before their title.
 * The arrow keys on a grip move its panel one place earlier or later: dnd-kit's own keyboard sensor
 * picks targets by position, which goes wrong when wide and half-width panels are mixed.
 */
export default function SortablePanels({
  items,
  order,
  onChange,
}: {
  items: PanelItem[];
  order: string[];
  onChange: (order: string[]) => void;
}) {
  const known = new Set(items.map((i) => i.id));
  const saved = order.filter((id) => known.has(id));
  const ids = [...saved, ...items.map((i) => i.id).filter((id) => !saved.includes(id))];
  const byId = new Map(items.map((i) => [i.id, i]));
  const sensors = useSensors(useSensor(PointerSensor));

  function onDragEnd({ active, over }: DragEndEvent) {
    if (over && active.id !== over.id) {
      onChange(arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id))));
    }
  }

  function step(id: string, by: number) {
    const from = ids.indexOf(id);
    const to = from + by;
    if (to >= 0 && to < ids.length) onChange(arrayMove(ids, from, to));
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={onDragEnd}
      accessibility={{ screenReaderInstructions: { draggable: "Drag to move this panel, or press the arrow keys to move it earlier or later." } }}
    >
      <SortableContext items={ids} strategy={rectSortingStrategy}>
        <div className="grid gap-4 lg:grid-cols-2">
          {ids.map((id) => (
            <Sortable key={id} item={byId.get(id)!} step={(by) => step(id, by)} />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

function Sortable({ item, step }: { item: PanelItem; step: (by: number) => void }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: item.id });
  const handle = (title: string) => (
    <button
      type="button"
      ref={setActivatorNodeRef}
      {...attributes}
      {...listeners}
      onKeyDown={(e) => {
        const by = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 }[e.key];
        if (!by) return;
        e.preventDefault();
        const button = e.currentTarget;
        step(by);
        requestAnimationFrame(() => button.focus());
      }}
      aria-label={`Move ${title}`}
      title="Drag to move"
      className="-ml-1 cursor-grab touch-none rounded p-1 text-ink-2 hover:bg-panel-sunk hover:text-ink active:cursor-grabbing"
    >
      <svg width="12" height="16" viewBox="0 0 12 16" fill="currentColor" aria-hidden="true">
        {[3, 8, 13].flatMap((y) => [<circle key={`a${y}`} cx="3" cy={y} r="1.5" />, <circle key={`b${y}`} cx="9" cy={y} r="1.5" />])}
      </svg>
    </button>
  );
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={`min-w-0 *:h-full ${item.wide ? "lg:col-span-2" : ""} ${isDragging ? "relative z-10 rounded-2xl opacity-80 shadow-2xl" : ""}`}
    >
      <DragHandle.Provider value={handle}>{item.node}</DragHandle.Provider>
    </div>
  );
}
