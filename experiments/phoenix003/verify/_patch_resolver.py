p='vcommon.py'; s=open(p,encoding='utf-8').read()
old='''        order = [f for f, s in self.stratum.items() if s == "core"]
        order += [f for f, s in self.stratum.items() if s == "extension"]
        order += [f for f in self.brand if f not in order]
        self.order = order

    def resolve(self, applicant):
        tokset = set(tokens(applicant))
        if not tokset:
            return None, None
        for firm in self.order:
            spec = self.brand[firm]
            hits = tokset & set(spec.get("any_token", []))
            if not hits:
                continue
            quals = spec.get("qualifier_tokens")
            if quals and not (tokset & set(quals)):
                continue
            return firm, sorted(hits)[0]
        return None, None'''
new='''        order = [f for f, s in self.stratum.items() if s == "core"]
        order += [f for f, s in self.stratum.items() if s == "extension"]
        order += [f for f in self.brand if f not in order]
        self.order = order
        # lineage v3: per-firm exclusion substrings (e.g. ZIMMER + MEDIZINSYSTEME is a
        # different company). Matched against the normalised applicant string.
        self.exclusions = {}
        for f, spec in self.brand.items():
            ex = [norm(x) for x in (spec.get("exclude_if_contains") or []) if x]
            if ex:
                self.exclusions[f] = ex

    def resolve(self, applicant):
        tokset = set(tokens(applicant))
        if not tokset:
            return None, None
        ntext = " " + norm(applicant) + " "
        for firm in self.order:
            spec = self.brand[firm]
            hits = tokset & set(spec.get("any_token", []))
            if not hits:
                continue
            quals = spec.get("qualifier_tokens")
            if quals and not (tokset & set(quals)):
                continue
            excluded = False
            for x in self.exclusions.get(firm, []):
                if (" " + x + " ") in ntext:
                    excluded = True
                    break
            if excluded:
                continue
            return firm, sorted(hits)[0]
        return None, None'''
assert old in s
s=s.replace(old,new)
# all_matching_firms should honour exclusions too
old2='''    def all_matching_firms(self, applicant):
        tokset = set(tokens(applicant))
        out = []
        for firm in self.order:
            spec = self.brand[firm]
            hits = tokset & set(spec.get("any_token", []))
            if not hits:
                continue
            quals = spec.get("qualifier_tokens")
            if quals and not (tokset & set(quals)):
                continue
            out.append(firm)
        return out'''
new2='''    def all_matching_firms(self, applicant):
        tokset = set(tokens(applicant))
        ntext = " " + norm(applicant) + " "
        out = []
        for firm in self.order:
            spec = self.brand[firm]
            hits = tokset & set(spec.get("any_token", []))
            if not hits:
                continue
            quals = spec.get("qualifier_tokens")
            if quals and not (tokset & set(quals)):
                continue
            if any((" " + x + " ") in ntext for x in self.exclusions.get(firm, [])):
                continue
            out.append(firm)
        return out'''
assert old2 in s
s=s.replace(old2,new2)
open(p,'w',encoding='utf-8').write(s); print('patched resolver')
