/**
 * Reports which documentation section is in view, for the contents list.
 *
 * A section counts as "in view" while it overlaps a band starting just under the sticky header and
 * ending before the middle of the viewport. The active section is the first in document order that
 * is in view; when none is (a long gap between headings), the previous one stays active.
 */
export function observeSections(
	root: ParentNode,
	ids: readonly string[],
	onActive: (id: string) => void
): () => void {
	if (typeof IntersectionObserver === 'undefined') return () => {};
	const inView: string[] = [];
	const observer = new IntersectionObserver(
		(entries) => {
			for (const entry of entries) {
				const at = inView.indexOf(entry.target.id);
				if (entry.isIntersecting && at < 0) inView.push(entry.target.id);
				if (!entry.isIntersecting && at >= 0) inView.splice(at, 1);
			}
			const first = ids.find((id) => inView.includes(id));
			if (first) onActive(first);
		},
		{ rootMargin: '-120px 0px -55% 0px' }
	);
	for (const id of ids) {
		const section = root.querySelector(`#${CSS.escape(id)}`);
		if (section) observer.observe(section);
	}
	return () => observer.disconnect();
}
