type Sectioned = { section?: string };

/** Steps are stored in one list; neighbours with the same section name belong together. */
export function sections<T extends Sectioned>(steps: T[]): { name: string; steps: T[] }[] {
  const out: { name: string; steps: T[] }[] = [];
  for (const step of steps) {
    const name = step.section ?? "";
    const last = out.at(-1);
    if (last?.name === name) last.steps.push(step);
    else out.push({ name, steps: [step] });
  }
  return out;
}
