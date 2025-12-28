import ast
import hashlib
import python_minifier
import binascii
import random
import string


class ImportRenamer(ast.NodeTransformer):
    """
    1) For every import/import-from without an asname, create an alias (e.g. import uuid -> import uuid as _a1b2)
    2) Record mapping original_name -> alias_name (original_name is the simple name that appears in code)
    3) Rewrite all Name nodes (loads) that refer to those original imports to use the alias, unless the name is
       shadowed by a local binding in the current scope.
    4) Update Global/Nonlocal declarations that name the original imports to the alias.
    """

    def __init__(self, seed: int | None = None):
        self.name_map: dict[str, str] = {}  # original -> alias
        self.scopes: list[set[str]] = []  # stack of sets: bound names in each scope
        self.random = random.Random(seed)

    # ----------------------
    # Alias generation
    # ----------------------
    def _make_alias(self, name: str) -> str:
        # Example deterministic-ish alias: _<4-hex-hash><3-randomletters>
        h = hashlib.md5(name.encode("utf8")).hexdigest()[:6]
        suf = "".join(self.random.choices(string.ascii_lowercase, k=3))
        return f"_{h}{suf}"

    # ----------------------
    # Scope helpers
    # ----------------------
    def _push_scope(self):
        self.scopes.append(set())

    def _pop_scope(self):
        self.scopes.pop()

    def _bind_name(self, name: str):
        if not self.scopes:
            self._push_scope()
        self.scopes[-1].add(name)

    def _is_bound_in_any_scope(self, name: str) -> bool:
        # If name is bound in the current scope or any enclosing scope, return True
        for s in reversed(self.scopes):
            if name in s:
                return True
        return False

    # ----------------------
    # Visitors that create aliases and record bindings
    # ----------------------
    def visit_Module(self, node: ast.Module):
        # create top-level scope
        self._push_scope()
        # visit imports (visit_Import / visit_ImportFrom will create aliases and bind alias names)
        self.generic_visit(node)
        return node

    def visit_Import(self, node: ast.Import):
        # For each alias in "import foo as bar" if asname is None -> create alias, record mapping,
        # and mark alias as bound in current scope.
        for alias in node.names:
            # the name commonly used in code is the top-level part (e.g. "os.path" -> "os")
            used_name = alias.asname or alias.name.split(".")[0]
            if alias.asname is None:
                new_as = self._make_alias(used_name)
                alias.asname = new_as
                # map the original used name (top-level) -> new alias
                self.name_map[used_name] = new_as
            else:
                # if already has asname, still record mapping from original used_name -> asname
                self.name_map[used_name] = alias.asname
            # mark the alias as bound at this scope
            self._bind_name(alias.asname)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom):
        # For "from pkg import a as b" -> record mapping a -> asname (or generated asname)
        for alias in node.names:
            if alias.asname is None:
                new_as = self._make_alias(alias.name)
                alias.asname = new_as
                self.name_map[alias.name] = new_as
            else:
                self.name_map[alias.name] = alias.asname
            # bind the alias in current scope
            self._bind_name(alias.asname)
        return node

    # ----------------------
    # Bindings: function/class/assign/args/etc.
    # ----------------------
    def visit_FunctionDef(self, node: ast.FunctionDef):
        # function name is bound in current scope
        self._bind_name(node.name)
        # new inner scope for the function body
        self._push_scope()
        # arguments bind names in the function scope
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self._bind_name(arg.arg)
        if node.args.vararg:
            self._bind_name(node.args.vararg.arg)
        if node.args.kwarg:
            self._bind_name(node.args.kwarg.arg)
        # process decorator list and body
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        node.body = [self.visit(n) for n in node.body]
        self._pop_scope()
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        # same handling as FunctionDef
        self._bind_name(node.name)
        self._push_scope()
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self._bind_name(arg.arg)
        if node.args.vararg:
            self._bind_name(node.args.vararg.arg)
        if node.args.kwarg:
            self._bind_name(node.args.kwarg.arg)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        node.body = [self.visit(n) for n in node.body]
        self._pop_scope()
        return node

    def visit_ClassDef(self, node: ast.ClassDef):
        # class name bound in current scope
        self._bind_name(node.name)
        # class body gets its own scope
        self._push_scope()
        node.bases = [self.visit(b) for b in node.bases]
        node.keywords = [self.visit(k) for k in node.keywords]
        node.body = [self.visit(n) for n in node.body]
        self._pop_scope()
        return node

    def visit_Assign(self, node: ast.Assign):
        # Bind names that are assignment targets BEFORE visiting the value so they shadow replacement in body
        for target in node.targets:
            for n in self._target_names(target):
                self._bind_name(n)
        node.targets = [self.visit(t) for t in node.targets]
        node.value = self.visit(node.value) if node.value is not None else None
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.target is not None:
            for n in self._target_names(node.target):
                self._bind_name(n)
        node.target = self.visit(node.target)
        node.annotation = (
            self.visit(node.annotation) if node.annotation is not None else None
        )
        node.value = self.visit(node.value) if node.value is not None else None
        return node

    def visit_AugAssign(self, node: ast.AugAssign):
        for n in self._target_names(node.target):
            self._bind_name(n)
        node.target = self.visit(node.target)
        node.value = self.visit(node.value)
        return node

    def visit_For(self, node: ast.For):
        for n in self._target_names(node.target):
            self._bind_name(n)
        node.target = self.visit(node.target)
        node.iter = self.visit(node.iter)
        self._push_scope()
        node.body = [self.visit(n) for n in node.body]
        node.orelse = [self.visit(n) for n in node.orelse]
        self._pop_scope()
        return node

    def visit_With(self, node: ast.With):
        for item in node.items:
            if item.optional_vars is not None:
                for n in self._target_names(item.optional_vars):
                    self._bind_name(n)
        node.items = [self.visit(i) for i in node.items]
        self._push_scope()
        node.body = [self.visit(n) for n in node.body]
        self._pop_scope()
        return node

    def visit_ListComp(self, node: ast.ListComp):
        # comprehensions have their own inner scope for targets
        self._push_scope()
        node.generators = [self.visit(g) for g in node.generators]
        node.elt = self.visit(node.elt)
        self._pop_scope()
        return node

    def visit_comprehension(self, node: ast.comprehension):
        for n in self._target_names(node.target):
            self._bind_name(n)
        node.target = self.visit(node.target)
        node.iter = self.visit(node.iter)
        node.ifs = [self.visit(i) for i in node.ifs]
        return node

    def visit_arg(self, node: ast.arg):
        # args are already recorded in visit_FunctionDef, but visiting is fine
        return node

    def visit_Global(self, node: ast.Global):
        # if global mentions an original import name, change it to the alias so it points to the module-level alias
        new_names = []
        for n in node.names:
            if n in self.name_map:
                new_names.append(self.name_map[n])
            else:
                new_names.append(n)
        node.names = new_names
        return node

    def visit_Nonlocal(self, node: ast.Nonlocal):
        # similarly remap nonlocal declarations if they reference an original imported name
        new_names = []
        for n in node.names:
            if n in self.name_map:
                new_names.append(self.name_map[n])
            else:
                new_names.append(n)
        node.names = new_names
        return node

    # ----------------------
    # Replace Name usages (loads) with alias when appropriate
    # ----------------------
    def visit_Name(self, node: ast.Name):
        # Do not remap when this is being assigned to (Store/Del) — only for Load we try to replace.
        if isinstance(node.ctx, ast.Load):
            orig = node.id
            if orig in self.name_map and (not self._is_bound_in_any_scope(orig)):
                # replace
                new_id = self.name_map[orig]
                return ast.copy_location(ast.Name(id=new_id, ctx=node.ctx), node)
        # For Store/Del just return node (we already registered bindings earlier)
        return node

    # ----------------------
    # Helpers
    # ----------------------
    def _target_names(self, target) -> list[str]:
        """Return a list of simple names bound by target (e.g. Name nodes inside tuples etc)."""
        names = []
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                names.extend(self._target_names(elt))
        elif isinstance(target, ast.Attribute):
            # attribute assignment (obj.attr) does not bind a local name
            pass
        elif isinstance(target, ast.Subscript):
            # subscript assignment does not bind new name
            pass
        else:
            # other cases: ignore
            pass
        return names


class StringToHexTransformer(ast.NodeTransformer):
    """
    Replace string literals with ''.join([chr(int("<hex>"[i:i+2], 16)) for i in range(0, len("<hex>"), 2)]).
    Keeps docstrings and f-strings safe.
    """

    def __init__(self, skip_docstrings=True, skip_fstrings=True):
        self.skip_docstrings = skip_docstrings
        self.skip_fstrings = skip_fstrings

    def _string_to_expr(self, s: str) -> ast.AST:
        # Convert to hex
        hexstr = binascii.hexlify(s.encode("utf-8")).decode("UTF-8")

        # Build comprehension:
        # ''.join([chr(int("<hex>"[i:i+2], 16)) for i in range(0, len("<hex>"), 2)])
        # Step-by-step AST build:

        # range(0, len("<hex>"), 2)
        range_call = ast.Call(
            func=ast.Name(id="range", ctx=ast.Load()),
            args=[
                ast.Constant(value=0),
                ast.Call(
                    func=ast.Name(id="len", ctx=ast.Load()),
                    args=[ast.Constant(value=hexstr)],
                    keywords=[],
                ),
                ast.Constant(value=2),
            ],
            keywords=[],
        )

        # chr(int("<hex>"[i:i+2], 16))
        slice_expr = ast.Subscript(
            value=ast.Constant(value=hexstr),
            slice=ast.Slice(
                lower=ast.Name(id="i", ctx=ast.Load()),
                upper=ast.BinOp(
                    left=ast.Name(id="i", ctx=ast.Load()),
                    op=ast.Add(),
                    right=ast.Constant(value=2),
                ),
            ),
            ctx=ast.Load(),
        )
        int_call = ast.Call(
            func=ast.Name(id="int", ctx=ast.Load()),
            args=[slice_expr, ast.Constant(value=16)],
            keywords=[],
        )
        chr_call = ast.Call(
            func=ast.Name(id="chr", ctx=ast.Load()), args=[int_call], keywords=[]
        )

        # List comprehension: [chr(int(...)) for i in range(...)]
        comp = ast.ListComp(
            elt=chr_call,
            generators=[
                ast.comprehension(
                    target=ast.Name(id="i", ctx=ast.Store()),
                    iter=range_call,
                    ifs=[],
                    is_async=0,
                )
            ],
        )

        # ''.join([...])
        join_call = ast.Call(
            func=ast.Attribute(
                value=ast.Constant(value=""), attr="join", ctx=ast.Load()
            ),
            args=[comp],
            keywords=[],
        )

        return join_call

    def _transform_body(self, body):
        if not body:
            return body
        new_body = []
        for idx, stmt in enumerate(body):
            if (
                idx == 0
                and self.skip_docstrings
                and isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                new_body.append(stmt)
                continue
            new_body.append(self.visit(stmt))
        return new_body

    def visit_Module(self, node):
        node.body = self._transform_body(node.body)
        return node

    def visit_FunctionDef(self, node):
        node.body = self._transform_body(node.body)
        return node

    def visit_AsyncFunctionDef(self, node):
        node.body = self._transform_body(node.body)
        return node

    def visit_ClassDef(self, node):
        node.body = self._transform_body(node.body)
        return node

    def visit_JoinedStr(self, node):
        if self.skip_fstrings:
            return node
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            new_node = self._string_to_expr(node.value)
            ast.copy_location(new_node, node)
            return new_node
        return node


def gen_random_name(n=8):
    return "n" + "".join(random.choices(string.digits + string.ascii_letters, k=n))


class Renamer(ast.NodeTransformer):
    """
    Per-binding obfuscation:
      - each binding (assign target, arg, comprehension target, def/class name, import asname) gets a fresh random name
      - uses (ast.Name loads) are rewritten to the corresponding name valid in the current lexical scope
    Correctly handles comprehensions/generator expressions to avoid target/use mismatches.
    """

    def __init__(self, seed=None):
        self.scopes = []  # list of dicts mapping original -> obfuscated in each scope
        if seed is not None:
            random.seed(seed)

    # scope helpers
    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        self.scopes.pop()

    def bind_name(self, orig):
        # create mapping in current scope for this binding
        if not self.scopes:
            self.push_scope()
        mapping = self.scopes[-1]
        if orig not in mapping:
            mapping[orig] = gen_random_name()
        return mapping[orig]

    def lookup(self, orig):
        # find nearest mapping for orig, from inner->outer
        for m in reversed(self.scopes):
            if orig in m:
                return m[orig]
        return None

    # --- Module / top-level ---
    def visit_Module(self, node):
        self.push_scope()
        self.generic_visit(node)
        self.pop_scope()
        return node

    # --- Function / Class definitions ---
    def visit_FunctionDef(self, node):
        # function name bound in current (enclosing) scope
        obf_name = self.bind_name(node.name)
        node.name = obf_name

        # new function scope
        self.push_scope()
        # bind args
        for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            self.bind_name(a.arg)
            a.arg = self.lookup(a.arg)
        if node.args.vararg:
            self.bind_name(node.args.vararg.arg)
            node.args.vararg.arg = self.lookup(node.args.vararg.arg)
        if node.args.kwarg:
            self.bind_name(node.args.kwarg.arg)
            node.args.kwarg.arg = self.lookup(node.args.kwarg.arg)

        # decorators, returns, body
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        if node.returns:
            node.returns = self.visit(node.returns)
        node.body = [self.visit(n) for n in node.body]

        self.pop_scope()
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        obf_name = self.bind_name(node.name)
        node.name = obf_name
        self.push_scope()
        node.bases = [self.visit(b) for b in node.bases]
        node.keywords = [self.visit(k) for k in node.keywords]
        node.body = [self.visit(n) for n in node.body]
        self.pop_scope()
        return node

    # --- Lambdas ---
    def visit_Lambda(self, node):
        # lambdas have their own tiny scope
        self.push_scope()
        for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            self.bind_name(a.arg)
            a.arg = self.lookup(a.arg)
        if node.args.vararg:
            self.bind_name(node.args.vararg.arg)
            node.args.vararg.arg = self.lookup(node.args.vararg.arg)
        if node.args.kwarg:
            self.bind_name(node.args.kwarg.arg)
            node.args.kwarg.arg = self.lookup(node.args.kwarg.arg)
        node.body = self.visit(node.body)
        self.pop_scope()
        return node

    # --- Assignments & target binding ---
    def _collect_target_names(self, target):
        """Return simple names bound by a target (Name nodes inside tuple/list etc.)."""
        names = []
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                names.extend(self._collect_target_names(elt))
        # attributes/subscripts don't bind new local names
        return names

    def _apply_target_renames(self, target):
        """Apply renames in-place for a target that's already been bind_name'd."""
        if isinstance(target, ast.Name):
            new = self.lookup(target.id)
            if new:
                target.id = new
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._apply_target_renames(elt)

    def visit_Assign(self, node):
        # Bind targets first so they shadow inside value if necessary
        for t in node.targets:
            for n in self._collect_target_names(t):
                self.bind_name(n)
        # Now apply renames to targets and visit them
        node.targets = [self.visit(t) for t in node.targets]
        for t in node.targets:
            self._apply_target_renames(t)
        node.value = self.visit(node.value) if node.value is not None else None
        return node

    def visit_AnnAssign(self, node):
        if node.target is not None:
            for n in self._collect_target_names(node.target):
                self.bind_name(n)
        node.target = self.visit(node.target)
        if isinstance(node.target, (ast.Tuple, ast.List)) or isinstance(
            node.target, ast.Name
        ):
            self._apply_target_renames(node.target)
        node.annotation = self.visit(node.annotation) if node.annotation else None
        node.value = self.visit(node.value) if node.value else None
        return node

    def visit_AugAssign(self, node):
        for n in self._collect_target_names(node.target):
            self.bind_name(n)
        node.target = self.visit(node.target)
        self._apply_target_renames(node.target)
        node.value = self.visit(node.value)
        return node

    # --- For / With targets ---
    def visit_For(self, node):
        # visit iter first (target is not bound for iter)
        node.iter = self.visit(node.iter)
        # bind target names then apply rename
        for n in self._collect_target_names(node.target):
            self.bind_name(n)
        node.target = self.visit(node.target)
        self._apply_target_renames(node.target)
        # body has a new nested scope (but typical Python keeps same scope for for-body; we do push for safety)
        self.push_scope()
        node.body = [self.visit(n) for n in node.body]
        node.orelse = [self.visit(n) for n in node.orelse]
        self.pop_scope()
        return node

    def visit_With(self, node):
        for item in node.items:
            if item.optional_vars is not None:
                for n in self._collect_target_names(item.optional_vars):
                    self.bind_name(n)
        node.items = [self.visit(i) for i in node.items]
        self.push_scope()
        node.body = [self.visit(n) for n in node.body]
        self.pop_scope()
        return node

    # --- Comprehensions & generator expressions ---
    def visit_comprehension(self, node):
        # Visit iter BEFORE binding the comprehension target(s)
        node.iter = self.visit(node.iter)

        # Create new inner scope for the comprehension level and bind the target names
        # Note: we use the push/pop done in the surrounding ListComp/GeneratorExp visitors
        target_names = self._collect_target_names(node.target)
        for n in target_names:
            self.bind_name(n)
        # Now apply the rename to the AST target node
        self._apply_target_renames(node.target)

        # Now visit any ifs (they see the target bound)
        node.ifs = [self.visit(i) for i in node.ifs]
        return node

    def visit_ListComp(self, node):
        self.push_scope()
        node.generators = [
            self.visit(g) for g in node.generators
        ]  # visit_comprehension handles binding
        node.elt = self.visit(node.elt)
        self.pop_scope()
        return node

    def visit_GeneratorExp(self, node):
        self.push_scope()
        node.generators = [self.visit(g) for g in node.generators]
        node.elt = self.visit(node.elt)
        self.pop_scope()
        return node

    def visit_SetComp(self, node):
        self.push_scope()
        node.generators = [self.visit(g) for g in node.generators]
        node.elt = self.visit(node.elt)
        self.pop_scope()
        return node

    def visit_DictComp(self, node):
        self.push_scope()
        node.generators = [self.visit(g) for g in node.generators]
        node.key = self.visit(node.key)
        node.value = self.visit(node.value)
        self.pop_scope()
        return node

    # --- Imports: bind the asname (or generate one) ---
    def visit_Import(self, node):
        for alias in node.names:
            used_name = alias.asname or alias.name.split(".")[0]
            if alias.asname is None:
                new_as = self.bind_name(used_name)
                alias.asname = new_as
            else:
                # record given asname as binding in scope
                self.bind_name(alias.asname)
        return node

    def visit_ImportFrom(self, node):
        for alias in node.names:
            used_name = alias.asname or alias.name
            if alias.asname is None:
                new_as = self.bind_name(used_name)
                alias.asname = new_as
            else:
                self.bind_name(alias.asname)
        return node

    # --- Name usage replacement ---
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            mapped = self.lookup(node.id)
            if mapped:
                return ast.copy_location(ast.Name(id=mapped, ctx=node.ctx), node)
        return node

    # generic visit fallback
    def generic_visit(self, node):
        return super().generic_visit(node)


src = ""

with open("password_game.py", "r") as f:
    src = f.read()

tree = ast.parse(src)
renamer = Renamer()
new_tree = renamer.visit(tree)
ast.fix_missing_locations(new_tree)
tr = StringToHexTransformer()
new = tr.visit(tree)
ast.fix_missing_locations(new)
three = ImportRenamer()
new_three = three.visit(tree)
ast.fix_missing_locations(new_three)


minified = python_minifier.minify(
    ast.unparse(new),
    remove_literal_statements=True,
    remove_annotations=True,
    remove_pass=False,
    rename_locals=False,
    rename_globals=False,
    remove_explicit_return_none=False,
    convert_posargs_to_args=True,
)

print(minified)
