"use client";

import { useEffect, useState } from "react";
import { actorAt, ROOM, type ActorFrame, type ActorId, type Pose } from "@/lib/rotina";

const NAMES: Record<ActorId, string> = {
  ceo: "Regente",
  cio: "Mestre das Missões",
  cco: "Vigia do Fosso",
};

type Props = {
  paused: boolean;
  selected: ActorId | null;
  onSelect: (id: ActorId) => void;
};

function diamond(cx: number, cy: number, w: number, h: number): string {
  return `${cx},${cy - h} ${cx + w},${cy} ${cx},${cy + h} ${cx - w},${cy}`;
}

function Floor() {
  const tiles = [];
  for (let row = 0; row < 9; row += 1) {
    for (let col = 0; col < 14; col += 1) {
      const cx = 200 + (col - row) * 16;
      const cy = 58 + (col + row) * 8;
      if (cx < 8 || cx > 392 || cy < 48 || cy > 214) continue;
      const dark = (col + row) % 2 === 0;
      tiles.push(
        <polygon
          key={`${col}-${row}`}
          points={diamond(cx, cy, 16, 8)}
          fill={dark ? "#3d4d64" : "#314054"}
          stroke="#243140"
          strokeWidth={0.4}
        />,
      );
    }
  }
  return <g>{tiles}</g>;
}

function Desk({ x, y, screen }: { x: number; y: number; screen: string }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={0} y={10} width={36} height={8} fill="#5c3a20" />
      <rect x={2} y={0} width={32} height={12} fill="#8a5a32" />
      <rect x={4} y={2} width={16} height={8} fill="#1c2430" />
      <rect x={6} y={4} width={8} height={1} fill="#7CFF6B" />
      <rect x={6} y={6} width={5} height={1} fill={screen} />
      <rect x={22} y={4} width={8} height={3} fill="#d8d0c4" />
      <rect x={8} y={12} width={10} height={2} fill="#2a241c" />
      <rect x={0} y={18} width={3} height={8} fill="#5c3a20" />
      <rect x={33} y={18} width={3} height={8} fill="#5c3a20" />
      <rect x={-2} y={20} width={8} height={6} fill="#2c3340" />
      <rect x={-1} y={16} width={6} height={4} fill="#3a4454" />
    </g>
  );
}

function Cubicle({ x, y, w }: { x: number; y: number; w: number }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={4} fill="#d5dbe3" />
      <rect x={x} y={y + 4} width={3} height={22} fill="#9aa3b2" />
      <rect x={x + w - 3} y={y + 4} width={3} height={22} fill="#9aa3b2" />
      <rect x={x + 6} y={y + 6} width={4} height={5} fill="#f4f0e6" />
      <rect x={x + 8} y={y + 8} width={6} height={1} fill="#7CFF6B" />
    </g>
  );
}

function Phone({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={0} y={4} width={16} height={6} fill="#5c3a20" />
      <rect x={2} y={0} width={12} height={5} fill="#2a2f38" />
      <rect x={3} y={1} width={4} height={2} fill="#1a1d22" />
      <rect x={9} y={1} width={3} height={2} fill="#c4554a" />
    </g>
  );
}

function Hero({
  shirt,
  hair,
  pose,
  frame,
  crown,
  headset,
}: {
  shirt: string;
  hair: string;
  pose: Pose;
  frame: number;
  crown?: boolean;
  headset?: boolean;
}) {
  const step = frame % 2;
  const skin = "#e2b494";
  const ink = "#1a120e";
  return (
    <g>
      {crown ? (
        <g>
          <rect x={4} y={-2} width={6} height={2} fill="#e6c15a" />
          <rect x={4} y={-3} width={1} height={2} fill="#e6c15a" />
          <rect x={6.5} y={-4} width={1} height={2} fill="#e6c15a" />
          <rect x={9} y={-3} width={1} height={2} fill="#e6c15a" />
        </g>
      ) : null}
      <rect x={4} y={0} width={6} height={2} fill={hair} />
      <rect x={3} y={2} width={8} height={5} fill={skin} />
      <rect x={4} y={3} width={1} height={1} fill={ink} />
      <rect x={8} y={3} width={1} height={1} fill={ink} />
      {pose === "talk" && step === 0 ? <rect x={6} y={5} width={2} height={1} fill="#a14b45" /> : null}
      <rect x={3} y={7} width={8} height={6} fill={shirt} />
      <rect x={6} y={8} width={2} height={3} fill="#f2e7cf" />
      {pose === "phone" ? (
        <>
          <rect x={10} y={3} width={2} height={5} fill={skin} />
          <rect x={11} y={2} width={2} height={2} fill="#2a2f38" />
          <rect x={1} y={8} width={2} height={5} fill={shirt} />
        </>
      ) : pose === "type" ? (
        <>
          <rect x={1} y={11 + step} width={3} height={2} fill={skin} />
          <rect x={10} y={12 - step} width={3} height={2} fill={skin} />
          <rect x={2} y={14} width={10} height={2} fill="#4a5568" />
          <rect x={4} y={14} width={6} height={1} fill="#9ad7ff" />
        </>
      ) : (
        <>
          <rect x={1} y={8} width={2} height={5 + (pose === "walk" && step ? 1 : 0)} fill={shirt} />
          <rect x={11} y={8} width={2} height={5 + (pose === "walk" && !step ? 1 : 0)} fill={shirt} />
        </>
      )}
      <rect x={4} y={13} width={2} height={pose === "walk" && step ? 4 : 5} fill="#242018" />
      <rect x={8} y={13} width={2} height={pose === "walk" && !step ? 4 : 5} fill="#242018" />
      <rect x={3} y={18} width={3} height={2} fill="#141414" />
      <rect x={8} y={18} width={3} height={2} fill="#141414" />
      {headset ? (
        <>
          <rect x={2} y={3} width={1} height={3} fill="#d0d5de" />
          <rect x={11} y={3} width={1} height={3} fill="#d0d5de" />
          <rect x={2} y={2} width={10} height={1} fill="#d0d5de" />
        </>
      ) : null}
    </g>
  );
}

const LOOK: Record<ActorId, { shirt: string; hair: string; crown?: boolean; headset?: boolean }> = {
  ceo: { shirt: "#243044", hair: "#3a2a22", crown: true },
  cio: { shirt: "#2f6b3a", hair: "#6b3a22" },
  cco: { shirt: "#5a3d78", hair: "#1c1c1c", headset: true },
};

function ActorSprite({ actor, frame, selected }: { actor: ActorFrame; frame: number; selected: boolean }) {
  const look = LOOK[actor.id];
  return (
    <g transform={`translate(${actor.x} ${actor.y}) scale(${actor.face * 1.55} 1.55)`}>
      {selected ? <rect x={-9} y={-24} width={18} height={26} fill="none" stroke="#f2e27a" strokeWidth={0.8} /> : null}
      <g transform="translate(-7 -20)">
        <Hero shirt={look.shirt} hair={look.hair} pose={actor.pose} frame={frame} crown={look.crown} headset={look.headset} />
      </g>
    </g>
  );
}

export function SalaDoTrono({ paused, selected, onSelect }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [frame, setFrame] = useState(0);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    if (paused || reduced) return;
    const timer = window.setInterval(() => {
      setElapsed((value) => value + 140);
      setFrame((value) => value + 1);
    }, 140);
    return () => window.clearInterval(timer);
  }, [paused, reduced]);

  const actors = (["ceo", "cio", "cco"] as ActorId[])
    .map((id) => actorAt(id, reduced ? 0 : elapsed))
    .sort((a, b) => a.y - b.y);

  return (
    <div className="relative w-full overflow-visible border-4 border-[#101820] bg-[#243044] shadow-[6px_6px_0_#0c1018]">
      <svg
        viewBox={`0 0 ${ROOM.w} ${ROOM.h}`}
        role="img"
        aria-label="Sala do Trono, conselho em isometria"
        className="block h-auto w-full"
        shapeRendering="crispEdges"
      >
        <rect width={ROOM.w} height={ROOM.h} fill="#6e7e94" />
        <rect x={0} y={0} width={ROOM.w} height={36} fill="#5c6d84" />
        <rect x={18} y={6} width={28} height={22} fill="#9ec7e6" />
        <rect x={31} y={6} width={2} height={22} fill="#d5e4f2" />
        <rect x={18} y={6} width={28} height={2} fill="#efe6d4" />
        <rect x={360} y={4} width={14} height={14} fill="#efe6d4" />
        <rect x={366} y={6} width={1} height={5} fill="#1a120e" />
        <rect x={366} y={10} width={4} height={1} fill="#1a120e" />
        <rect x={150} y={8} width={28} height={16} fill="#6b2a32" />
        <rect x={154} y={12} width={20} height={2} fill="#e6c15a" />
        <text x={156} y={14} fill="#e6c15a" fontSize={6}>
          NQ
        </text>
        <Floor />
        <Cubicle x={58} y={62} w={52} />
        <Cubicle x={176} y={68} w={58} />
        <Cubicle x={276} y={96} w={58} />
        <Desk x={64} y={78} screen="#7CFF6B" />
        <Desk x={190} y={84} screen="#f2e27a" />
        <Desk x={292} y={112} screen="#ff8b7a" />
        <Phone x={112} y={146} />
        <Phone x={52} y={156} />
        <g transform="translate(40 150)">
          <rect x={4} y={6} width={8} height={8} fill="#5c3a20" />
          <rect x={2} y={2} width={12} height={5} fill="#2f6b3a" />
          <rect x={6} y={0} width={4} height={3} fill="#3f8f4c" />
        </g>
        {actors.map((actor) => (
          <ActorSprite key={actor.id} actor={actor} frame={frame} selected={selected === actor.id} />
        ))}
      </svg>
      {actors.map((actor) => (
        <button
          key={actor.id}
          type="button"
          onClick={() => onSelect(actor.id)}
          aria-pressed={selected === actor.id}
          aria-label={`${NAMES[actor.id]}. ${actor.label}`}
          className="absolute z-10 min-h-11 min-w-11 -translate-x-1/2 -translate-y-full border-0 bg-transparent p-0"
          style={{
            left: `${(actor.x / ROOM.w) * 100}%`,
            top: `${(actor.y / ROOM.h) * 100}%`,
            width: "12%",
            height: "22%",
          }}
        />
      ))}
      {actors.map((actor) =>
        selected === actor.id ? null : (
          <div
            key={`${actor.id}-tag`}
            className="pointer-events-none absolute z-20 max-w-[9.5rem] border-2 border-[#39ff6a] bg-[#07140c] px-1.5 py-1 text-[8px] leading-tight text-[#b6ff8a] sm:text-[9px]"
            style={{
              left: `${(actor.x / ROOM.w) * 100}%`,
              top: `${(actor.y / ROOM.h) * 100}%`,
              transform: "translate(-50%, calc(-100% - 3.2rem))",
            }}
          >
            ESTADO: {actor.label}
          </div>
        ),
      )}
    </div>
  );
}
