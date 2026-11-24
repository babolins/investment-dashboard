import { getContext, setContext } from "svelte";
import type { ConfigSummary } from "../types";

/** What CategoryManager shares with its recursive rows (so they need no prop threading). */
export interface ManagerContext {
  readonly config: ConfigSummary;
  readonly busy: boolean;
  readonly editing: string | null;
  readonly rowError: { name: string; message: string } | null;
  readonly dragged: string | null;
  readonly overTarget: string | null;
  /** Categories this one may move into: not itself, its descendants, or leaves holding securities. */
  moveTargets(name: string): string[];
  /** Whether the dragged node may be dropped on a category ("" = top level). */
  canDropOn(target: string): boolean;
  startDrag(name: string, e: DragEvent): void;
  endDrag(): void;
  dragOver(e: DragEvent, target: string): void;
  dragLeave(e: DragEvent, target: string): void;
  drop(e: DragEvent, target: string): Promise<void>;
  /** Resolves to whether the move succeeded. */
  move(name: string, parent: string | null): Promise<boolean>;
  remove(name: string): Promise<void>;
  startEdit(name: string): void;
  cancelEdit(): void;
  fail(name: string, message: string): void;
  save(name: string, patch: Patch): Promise<void>;
}

export type Patch = { name?: string; buy_symbol?: string | null; target?: number | null };

const KEY = Symbol("category-manager");

export const provideManager = (ctx: ManagerContext) => setContext(KEY, ctx);
export const useManager = () => getContext<ManagerContext>(KEY);
