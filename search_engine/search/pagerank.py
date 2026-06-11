# search/pagerank.py

from storage.database import Database
from collections import defaultdict

class PageRankCalculator:
    def __init__(self, damping_factor=0.85, max_iterations=100, tolerance=1e-6):
        self.damping_factor = damping_factor
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def calculate_and_save(self):
        db = Database()
        
        # 1. Build graph representation
        links = db.get_all_links()
        if not links:
            print("[PageRank] No links found. Skipping computation.")
            db.close()
            return

        out_degree = defaultdict(int)
        in_links = defaultdict(list)
        all_nodes = set()

        for source, target in links:
            all_nodes.add(source)
            all_nodes.add(target)
            out_degree[source] += 1
            in_links[target].append(source)

        N = len(all_nodes)
        print(f"[PageRank] Graph has {N} nodes and {len(links)} edges.")
        
        # 2. Initialize PageRank to 1/N
        pr = {node: 1.0 / N for node in all_nodes}
        
        # 3. Iterative computation
        for iteration in range(self.max_iterations):
            new_pr = {}
            max_diff = 0.0
            
            # Handle dangling nodes (nodes with 0 out_degree)
            dangling_sum = sum(pr[node] for node in all_nodes if out_degree[node] == 0)
            dangling_contrib = (self.damping_factor * dangling_sum) / N
            
            base_contrib = (1.0 - self.damping_factor) / N
            
            for node in all_nodes:
                # Sum of (PR(in_node) / out_degree(in_node))
                in_sum = 0.0
                for in_node in in_links[node]:
                    if out_degree[in_node] > 0:
                        in_sum += pr[in_node] / out_degree[in_node]
                
                # Formula with damping factor
                new_pr[node] = base_contrib + dangling_contrib + (self.damping_factor * in_sum)
                
                diff = abs(new_pr[node] - pr[node])
                if diff > max_diff:
                    max_diff = diff
            
            pr = new_pr
            
            if max_diff < self.tolerance:
                print(f"[PageRank] Converged after {iteration + 1} iterations (diff: {max_diff:.8f}).")
                break
        else:
            print(f"[PageRank] Stopped after reaching max {self.max_iterations} iterations.")

        # 4. Save to Database
        db.update_pageranks(pr)
        db.close()
        print("[PageRank] Updated documents table with PageRank scores.")

if __name__ == "__main__":
    prc = PageRankCalculator()
    prc.calculate_and_save()
