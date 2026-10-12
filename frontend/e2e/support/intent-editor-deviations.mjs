export function intentEditorDeviations(recorded) {
  const value = structuredClone(recorded);
  const added = [];
  for (const field of value.fields ?? []) {
    // The popup's options are proven through its roles; the recorded native option DOM is retired.
    field.menu = [];
    if (field.kind === 'goal') field.buttons = field.buttons.filter(([label]) => label !== 'Clear');
    if (field.kind === 'lines') {
      field.label = 'Expected outcome (optional)';
      if (field.boxes.length !== 1 || field.boxes[0]) {
        added.push(...field.buttons.filter(([label]) => label === '+ Add a line'));
        field.buttons = field.buttons.filter(([label]) => label !== '+ Add a line');
      }
      if (field.boxes.length === 1 && !field.boxes[0])
        field.buttons = field.buttons.filter(
          ([label]) => label !== 'Remove' && label !== '+ Add a line',
        );
    }
  }
  value.notes = value.notes?.filter((note) => !note.startsWith('Saved'));
  if (value.footer) {
    value.footer.hint = '';
    value.footer.buttons.unshift(...added);
    value.footer.buttons = value.footer.buttons.filter(
      ([label, inert]) => label !== 'Undo changes' || !inert,
    );
  }
  if (value.question) {
    const said = value.question.said;
    const count = said.match(/You gave (\d+) later directions/)?.[1] ?? '1';
    const since =
      said.match(/since (.*?), the/)?.[1] ??
      (value.fields[0]?.marks.includes('from your prompt')
        ? 'your first prompt'
        : 'saving your intent');
    value.question.said = `${count} later direction${count === '1' ? '' : 's'} since ${since}.`;
  }
  return value;
}
