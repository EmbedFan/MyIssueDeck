/* The query builder of the advanced search dialog (FEA-0010).
 *
 * It edits the search as the same JSON the API takes (see docs/advanced-search.md) and writes it
 * into the hidden field `query` of the form. The server checks the search; this script only
 * keeps the form from sending blocks that are still empty.
 */
function searchBuilder(initial, kinds, statuses) {
  let counter = 0;

  function fromJson(block) {
    const node = blank(block.group ? "group" : block.type || "text");
    node.op = block.op || "and";
    if (block.group) {
      node.group = block.group.map((child) => fromJson(child));
    } else if (node.type === "text") {
      node.mode = block.mode || "simple";
      node.value = block.value || "";
      const fields = block.fields || ["title", "body"];
      node.title = fields.includes("title");
      node.body = fields.includes("body");
      node.caseSensitive = !!block.case_sensitive;
    } else {
      node.values = (block.values || []).slice();
    }
    return node;
  }

  function blank(type) {
    return {
      id: ++counter, op: "and", type: type, mode: "simple", value: "",
      title: true, body: true, caseSensitive: false, values: [], group: [],
    };
  }

  function toJson(node) {
    let out;
    if (node.type === "group") {
      const group = clean(node.group);
      if (!group.length) return null;
      out = { group: group };
    } else if (node.type === "text") {
      if (!node.value.trim()) return null;
      const fields = [];
      if (node.title) fields.push("title");
      if (node.body) fields.push("body");
      if (!fields.length) return null;
      out = { type: "text", mode: node.mode, value: node.value, fields: fields };
      if (node.mode === "regex" && node.caseSensitive) out.case_sensitive = true;
    } else {
      if (!node.values.length) return null;
      out = { type: node.type, values: node.values.slice() };
    }
    return out;
  }

  // the first block that is left has no operator, whatever it was before
  function clean(nodes) {
    const blocks = [];
    nodes.forEach((node) => {
      const json = toJson(node);
      if (!json) return;
      if (blocks.length) json.op = node.op;
      blocks.push(json);
    });
    return blocks;
  }

  const items = ((initial && initial.items) || []).map((b) => fromJson(b));

  return {
    items: items.length ? items : [blank("text")],
    kinds: kinds,
    statuses: statuses,
    open: false,
    maxDepth: 2,

    addBlock(list, type) { list.push(blank(type)); },
    remove(list, index) { list.splice(index, 1); },
    move(list, index, step) {
      const target = index + step;
      if (target < 0 || target >= list.length) return;
      list.splice(target, 0, list.splice(index, 1)[0]);
    },
    toggleValue(node, value) {
      const at = node.values.indexOf(value);
      if (at >= 0) node.values.splice(at, 1); else node.values.push(value);
    },
    options(node) { return node.type === "kind" ? this.kinds : this.statuses; },

    json() {
      const blocks = clean(this.items);
      return blocks.length ? JSON.stringify({ items: blocks }) : "";
    },
    isEmpty() { return this.json() === ""; },
  };
}

window.searchBuilder = searchBuilder;
