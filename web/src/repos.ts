export type RepoRole =
  | "interface"
  | "cognition"
  | "contract"
  | "world"
  | "research"
  | "transport"
  | "perception"
  | "compute"
  | "workbench";

export type RepoNode = {
  name: string;
  role: string;
  layer: RepoRole;
  live: boolean;
  href: string;
  blurb: string;
};

export const REPOS: RepoNode[] = [
  {
    name: "throne-room",
    role: "Human interface",
    layer: "interface",
    live: true,
    href: "https://github.com/TheBabelDragon/throne-room",
    blurb: "Operator HUD. Chat is the first actuator, not a special architecture.",
  },
  {
    name: "self-state-kernel",
    role: "Agent self",
    layer: "cognition",
    live: true,
    href: "https://github.com/TheBabelDragon/self-state-kernel",
    blurb: "Identity, goals, attention, beliefs, continuity. Owns cognition state, not the LLM.",
  },
  {
    name: "metafield-operator-abi",
    role: "Brain ↔ world",
    layer: "contract",
    live: true,
    href: "https://github.com/TheBabelDragon/metafield-operator-abi",
    blurb: "Capability-based contract. Agent proposes. Engine validates and commits.",
  },
  {
    name: "metafield-engine",
    role: "World kernel",
    layer: "world",
    live: true,
    href: "https://github.com/TheBabelDragon/metafield-engine",
    blurb: "FieldTick, deltas, scheduler, replay. Brutally boring. No chatbot logic.",
  },
  {
    name: "metafield",
    role: "Research / spec",
    layer: "research",
    live: false,
    href: "https://github.com/TheBabelDragon/metafield",
    blurb: "Laboratory. Designs graduate into the engine when they are tested.",
  },
  {
    name: "BabelBus",
    role: "General messaging",
    layer: "transport",
    live: false,
    href: "https://github.com/TheBabelDragon/BabelBus",
    blurb: "Nervous system. Transport, not semantics. FieldTick still defines meaning.",
  },
  {
    name: "field-bus",
    role: "Field transport",
    layer: "transport",
    live: false,
    href: "https://github.com/TheBabelDragon/field-bus",
    blurb: "CAN / CAN-FD for physical nodes. Narrower than BabelBus.",
  },
  {
    name: "wifi-sensing-system",
    role: "WiFi perception",
    layer: "perception",
    live: true,
    href: "https://github.com/TheBabelDragon/wifi-sensing-system",
    blurb: "CSI organ. Emits PerceptionEvent, never owns the world.",
  },
  {
    name: "optical-body-s3",
    role: "Optical perception",
    layer: "perception",
    live: false,
    href: "https://github.com/TheBabelDragon/optical-body-s3",
    blurb: "Laser + BPW34 body. Physical organ, not an AI repo.",
  },
  {
    name: "echo-grid-ultrasonic-os",
    role: "Ultrasonic perception",
    layer: "perception",
    live: false,
    href: "https://github.com/TheBabelDragon/echo-grid-ultrasonic-os",
    blurb: "Phased ultrasonic array. Same PerceptionEvent path.",
  },
  {
    name: "hall-node-s3",
    role: "Hall node",
    layer: "perception",
    live: false,
    href: "https://github.com/TheBabelDragon/hall-node-s3",
    blurb: "Hall-array edge node on Field Bus.",
  },
  {
    name: "aurora-swarm-btc",
    role: "Distributed compute",
    layer: "compute",
    live: false,
    href: "https://github.com/TheBabelDragon/aurora-swarm-btc",
    blurb: "Swarm fabric. Many workers, not another brain.",
  },
  {
    name: "metafield-work",
    role: "Workbench",
    layer: "workbench",
    live: false,
    href: "https://github.com/TheBabelDragon/metafield-work",
    blurb: "Operator isolation experiments. Not the runtime.",
  },
];

export const LOOP_CONTRACT = [
  "Agent observes FieldTick",
  "SelfState produces Action",
  "Operator ABI validates Action",
  "Engine produces FieldDelta",
  "next FieldTick",
  "Agent observes it",
] as const;
