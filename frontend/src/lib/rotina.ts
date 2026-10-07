export type ActorId = "ceo" | "cio" | "cco";
export type Pose = "walk" | "type" | "phone" | "talk";

export type Beat = {
  x: number;
  y: number;
  pose: Pose;
  face: 1 | -1;
  ms: number;
  label: string;
};

export type ActorFrame = {
  id: ActorId;
  x: number;
  y: number;
  pose: Pose;
  face: 1 | -1;
  label: string;
};

export const ROOM = { w: 400, h: 230 };

const CEO: Beat[] = [
  { x: 92, y: 112, pose: "type", face: 1, ms: 4600, label: "NO TRONO" },
  { x: 128, y: 158, pose: "walk", face: 1, ms: 1700, label: "EM MARCHA" },
  { x: 128, y: 158, pose: "phone", face: -1, ms: 3200, label: "NO TELEFONE" },
  { x: 168, y: 132, pose: "walk", face: 1, ms: 1500, label: "EM MARCHA" },
  { x: 168, y: 132, pose: "talk", face: 1, ms: 2800, label: "COM O CIO" },
  { x: 92, y: 112, pose: "walk", face: -1, ms: 1700, label: "EM MARCHA" },
];

const CIO: Beat[] = [
  { x: 214, y: 118, pose: "type", face: 1, ms: 3800, label: "NAS MISSÕES" },
  { x: 188, y: 136, pose: "walk", face: -1, ms: 1400, label: "EM MARCHA" },
  { x: 188, y: 136, pose: "talk", face: -1, ms: 2800, label: "COM O REGENTE" },
  { x: 250, y: 96, pose: "walk", face: 1, ms: 1500, label: "EM MARCHA" },
  { x: 250, y: 96, pose: "type", face: -1, ms: 2600, label: "NO MAPA" },
  { x: 214, y: 118, pose: "walk", face: -1, ms: 1400, label: "EM MARCHA" },
];

const CCO: Beat[] = [
  { x: 312, y: 146, pose: "type", face: -1, ms: 4200, label: "NO FOSSO" },
  { x: 250, y: 168, pose: "walk", face: -1, ms: 1800, label: "EM MARCHA" },
  { x: 168, y: 176, pose: "walk", face: -1, ms: 1800, label: "EM MARCHA" },
  { x: 78, y: 168, pose: "phone", face: 1, ms: 3000, label: "NO TELEFONE" },
  { x: 150, y: 150, pose: "walk", face: 1, ms: 1600, label: "EM MARCHA" },
  { x: 150, y: 150, pose: "talk", face: 1, ms: 2400, label: "COM O REGENTE" },
  { x: 312, y: 146, pose: "walk", face: 1, ms: 2000, label: "EM MARCHA" },
];

export const ROUTINES: Record<ActorId, Beat[]> = {
  ceo: CEO,
  cio: CIO,
  cco: CCO,
};

export function actorAt(id: ActorId, elapsed: number): ActorFrame {
  const routine = ROUTINES[id];
  const total = routine.reduce((sum, beat) => sum + beat.ms, 0);
  let cursor = ((elapsed % total) + total) % total;
  for (let index = 0; index < routine.length; index += 1) {
    const beat = routine[index];
    if (cursor <= beat.ms) {
      const previous = routine[(index + routine.length - 1) % routine.length];
      const travel = Math.min(700, beat.ms);
      if (beat.pose === "walk" && cursor < travel) {
        const progress = cursor / travel;
        return {
          id,
          x: previous.x + (beat.x - previous.x) * progress,
          y: previous.y + (beat.y - previous.y) * progress,
          pose: "walk",
          face: beat.x >= previous.x ? 1 : -1,
          label: "EM MARCHA",
        };
      }
      return { id, x: beat.x, y: beat.y, pose: beat.pose, face: beat.face, label: beat.label };
    }
    cursor -= beat.ms;
  }
  const home = routine[0];
  return { id, x: home.x, y: home.y, pose: home.pose, face: home.face, label: home.label };
}
