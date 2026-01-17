# The-Pulse Entity System Improvement Roadmap

## Executive Summary

The-Pulse entity system has a solid foundation with GLiNER-based named entity recognition, a well-structured PostgreSQL schema (TrackedEntity, EntityMention, EntityRelationship), and NetworkX graph analysis capabilities. The architecture supports 10 relationship types with confidence scores and temporal metadata—features that many entity systems lack entirely. The Cytoscape.js export capability provides a path to sophisticated visualization.

However, the system is significantly underutilizing its existing capabilities. The UI confines entity information to a "small box" despite having graph data that could power rich visualizations. Entity resolution relies on simple case-insensitive string matching without fuzzy matching, alias handling, or coreference resolution. These gaps mean entities that refer to the same real-world thing ("Bob Smith", "Robert Smith", "he") remain fragmented, reducing the intelligence value of the collected data.

This roadmap prioritizes quick wins that maximize existing infrastructure before introducing new dependencies. The goal is a system where entities are properly resolved, relationships are clearly visualized, and users can explore connections intuitively—transforming raw mentions into actionable intelligence.

---

## Current State Assessment

### What Works Well

| Component | Strength | Notes |
|-----------|----------|-------|
| **GLiNER NER** | Modern, efficient extraction | Handles PERSON, ORG, LOCATION well |
| **Schema Design** | Well-normalized, extensible | TrackedEntity → EntityMention → Documents chain is solid |
| **Relationship Model** | 10 types with confidence + temporal data | More sophisticated than many production systems |
| **NetworkX Integration** | Full graph analysis available | Paths, centrality, communities ready to use |
| **Cytoscape.js Export** | Visualization-ready format | Can power rich UIs without additional tools |
| **Per-User Deduplication** | Prevents obvious duplicates | Case-insensitive constraint works for exact matches |

### What's Underutilized

| Capability | Current Use | Potential |
|------------|-------------|----------|
| **Graph Analysis** | Likely minimal UI exposure | Could power relationship exploration, path finding, importance ranking |
| **Confidence Scores** | Stored but not surfaced | Should drive UI decisions (hide low-confidence, highlight high) |
| **Temporal Metadata** | Stored but not visualized | Could show entity evolution over time |
| **Cytoscape.js** | Export exists | Could be full interactive graph UI |
| **Relationship Types** | 10 types defined | UI could filter/color by type |

### Critical Gaps

| Gap | Impact | Severity |
|-----|--------|----------|
| **No Fuzzy Matching** | "Bob Smith" ≠ "Robert Smith" | High |
| **No Alias Handling** | "IBM" ≠ "International Business Machines" | High |
| **No Coreference** | "he said" doesn't link to entity | Medium |
| **No Cross-User Resolution** | Same entity duplicated per user | Medium |
| **Unclear Relationship Extraction** | How are relationships detected? | Unknown |
| **UI Underutilization** | Graph data hidden in small box | High (UX) |

---

## Prioritized Improvement Roadmap

### Phase 1: Quick Wins (1-2 Weeks)

*Goal: Maximize existing capabilities with minimal new code*

---

#### 1.1 Surface Confidence Scores in UI

**Problem:** Confidence scores are stored but not shown to users. Low-confidence entities appear alongside high-confidence ones, creating noise and eroding trust.

**Solution:** Add visual confidence indicators throughout the UI.

**Implementation Notes:**
```python
# Example: Add confidence badge to entity display
def get_confidence_indicator(score: float) -> str:
    if score >= 0.9:
        return "●●●"  # High confidence
    elif score >= 0.7:
        return "●●○"  # Medium confidence
    else:
        return "●○○"  # Low confidence
```

- Show confidence as colored dots, bars, or percentage
- Allow filtering: "Show only high-confidence entities"
- Sort entity lists by confidence (highest first)
- Consider hiding entities below a threshold (e.g., < 0.5) by default

**Expected Impact:** Users immediately see data quality. Reduces cognitive load by de-emphasizing uncertain extractions.

---

#### 1.2 Expand Entity Display from "Small Box" to Entity Cards

**Problem:** Entity information is "shoved in a small box," making it hard to explore relationships and context.

**Solution:** Implement expandable entity cards with progressive disclosure.

**Implementation Notes:**

*Entity Card Structure:*
```
┌─────────────────────────────────────────┐
│ ● PERSON                    [●●●] 94%   │
│ Robert Mueller                          │
├─────────────────────────────────────────┤
│ 📊 23 mentions across 12 documents      │
│ 🔗 Connected to 8 other entities        │
│ 📅 First seen: 2024-01-15               │
├─────────────────────────────────────────┤
│ [Expand Relationships] [View Timeline]  │
└─────────────────────────────────────────┘
```

- Collapsed: Name, type icon, confidence, mention count
- Expanded: Relationships list, document links, temporal range
- Use existing TrackedEntity + EntityMention data (no new queries needed)

**Expected Impact:** Users can quickly assess entity importance and drill into details without page navigation.

---

#### 1.3 Add Basic Entity Filtering and Sorting

**Problem:** Users cannot easily find specific entities or focus on what matters.

**Solution:** Add filter/sort controls to entity lists.

**Implementation Notes:**

*Filters to add:*
- Entity type (PERSON, ORG, LOCATION)
- Confidence threshold (slider)
- Mention count ("Show entities with 5+ mentions")
- Date range ("Entities mentioned this week")

*Sorts to add:*
- Most mentions (importance proxy)
- Highest confidence
- Most recent
- Most connected (relationship count)

```python
# Example query modification
def get_filtered_entities(user_id, entity_type=None, min_confidence=0.5, min_mentions=1):
    query = TrackedEntity.query.filter_by(user_id=user_id)
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    if min_confidence:
        query = query.filter(TrackedEntity.confidence >= min_confidence)
    # Join to count mentions
    query = query.join(EntityMention).group_by(TrackedEntity.id)
    query = query.having(func.count(EntityMention.id) >= min_mentions)
    return query.all()
```

**Expected Impact:** Users find relevant entities faster. Power users can focus on high-value data.

---

#### 1.4 Expose NetworkX Analysis Results

**Problem:** NetworkX graph analysis (centrality, communities, paths) exists but isn't surfaced to users.

**Solution:** Add "importance" and "cluster" indicators to entity display.

**Implementation Notes:**

*What NetworkX can already compute:*
```python
import networkx as nx

# Assuming graph G is already built from EntityRelationship
centrality = nx.degree_centrality(G)  # Who's most connected?
betweenness = nx.betweenness_centrality(G)  # Who bridges groups?
communities = nx.community.louvain_communities(G)  # What clusters exist?
```

*How to surface:*
- Add "Importance Score" to entity cards (based on centrality)
- Color-code entities by community/cluster
- Add "Key Connectors" section showing high-betweenness entities
- Show "Shortest path" between two selected entities

**Expected Impact:** Users discover non-obvious relationships. "This person connects two otherwise separate groups" becomes visible.

---

### Phase 2: Core Enhancements (1-2 Months)

*Goal: Solve entity resolution and enable rich graph visualization*

---

#### 2.1 Implement Fuzzy Entity Matching

**Problem:** "Bob Smith" and "Robert Smith" are stored as separate entities despite likely being the same person. Simple string matching misses obvious duplicates.

**Solution:** Add fuzzy matching during entity creation/update to suggest or auto-merge similar entities.

**Implementation Notes:**

*Recommended approach: RapidFuzz library*
```python
from rapidfuzz import fuzz, process

def find_similar_entities(new_entity_name: str, existing_entities: list, threshold: int = 85):
    """
    Find existing entities that might match the new one.
    Returns list of (entity, similarity_score) tuples.
    """
    matches = process.extract(
        new_entity_name,
        [e.name for e in existing_entities],
        scorer=fuzz.token_sort_ratio,  # Handles word order differences
        score_cutoff=threshold
    )
    return [(existing_entities[i], score) for name, score, i in matches]

# Example usage during entity creation
def create_or_merge_entity(name: str, entity_type: str, user_id: int):
    existing = get_entities_by_type(user_id, entity_type)
    similar = find_similar_entities(name, existing, threshold=85)
    
    if similar:
        best_match, score = similar[0]
        if score >= 95:
            # Auto-merge: very high confidence
            return add_alias_to_entity(best_match, name)
        else:
            # Suggest merge: let user decide
            return {"action": "suggest_merge", "candidates": similar}
    else:
        # No match: create new
        return create_new_entity(name, entity_type, user_id)
```

*Key considerations:*
- Use `token_sort_ratio` for names (handles "John Smith" vs "Smith, John")
- Use `partial_ratio` for organizations (handles "IBM" vs "IBM Corporation")
- Consider phonetic matching (Soundex/Metaphone) for names
- Store merge decisions for learning

**Expected Impact:** 20-40% reduction in duplicate entities. Users spend less time manually merging.

---

#### 2.2 Add Alias/Synonym Support

**Problem:** Entities often have multiple names ("IBM" / "International Business Machines" / "Big Blue"). Without alias support, these appear as separate entities.

**Solution:** Extend TrackedEntity to support aliases.

**Implementation Notes:**

*Schema addition:*
```python
class EntityAlias(Base):
    __tablename__ = 'entity_aliases'
    
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('tracked_entities.id'), nullable=False)
    alias = Column(String(255), nullable=False)
    alias_type = Column(String(50))  # 'acronym', 'nickname', 'formal', 'misspelling'
    confidence = Column(Float, default=1.0)
    source = Column(String(50))  # 'manual', 'auto_detected', 'kb_linked'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Unique per entity (an alias can only belong to one entity per user)
    __table_args__ = (
        UniqueConstraint('entity_id', 'alias'),
    )
```

*Entity lookup now checks aliases:*
```python
def find_entity_by_name(name: str, user_id: int):
    # First try exact match on canonical name
    entity = TrackedEntity.query.filter_by(name=name, user_id=user_id).first()
    if entity:
        return entity
    
    # Then try aliases
    alias = EntityAlias.query.join(TrackedEntity).filter(
        EntityAlias.alias.ilike(name),
        TrackedEntity.user_id == user_id
    ).first()
    if alias:
        return alias.entity
    
    return None
```

*Pre-populate common aliases:*
- Build a dictionary of common org aliases ("IBM" → "International Business Machines")
- Add name variations for people ("Robert" → "Bob", "Rob", "Bobby")
- Consider external knowledge base linking (see Phase 3)

**Expected Impact:** Organizations and people with known aliases automatically resolve. Users can add custom aliases.

---

#### 2.3 Build Interactive Graph Visualization

**Problem:** Graph data exists (Cytoscape.js export capability) but the UI doesn't leverage it. Users can't visually explore entity relationships.

**Solution:** Implement an interactive graph view using Cytoscape.js.

**Implementation Notes:**

*Why Cytoscape.js (you already have export):*
- MIT licensed, well-documented
- Handles 1000+ nodes with proper layout algorithms
- Built-in filtering, zooming, panning
- Excellent extension ecosystem

*Key features to implement:*

```javascript
// Basic graph initialization
const cy = cytoscape({
  container: document.getElementById('graph-container'),
  elements: entityGraphData,  // Your existing export!
  style: [
    {
      selector: 'node[type="PERSON"]',
      style: {
        'background-color': '#4A90D9',
        'label': 'data(name)',
        'width': 'mapData(mentions, 1, 100, 20, 60)',  // Size by mentions
      }
    },
    {
      selector: 'node[type="ORG"]',
      style: { 'background-color': '#7CB342' }
    },
    {
      selector: 'edge',
      style: {
        'width': 'mapData(confidence, 0, 1, 1, 5)',  // Thickness by confidence
        'line-color': '#999',
        'label': 'data(relationship_type)'
      }
    }
  ],
  layout: { name: 'cose' }  // Force-directed layout
});
```

*Solving the "hairball problem":*
1. **Progressive loading:** Start with top 20 entities by centrality
2. **Expand on click:** Click node to show its direct connections
3. **Filter by type:** Toggle PERSON/ORG/LOCATION visibility
4. **Filter by confidence:** Slider to hide weak connections
5. **Search to focus:** Search highlights node and dims others

*Layout recommendations:*
- Use `cose-bilkent` extension for better force-directed layout
- Implement "combo nodes" to collapse communities
- Add timeline slider for temporal filtering

**Expected Impact:** Users can visually explore relationships, discover hidden connections, and understand entity networks at a glance.

---

#### 2.4 Implement Manual Entity Merge UI

**Problem:** Even with fuzzy matching, some duplicates will slip through. Users need a way to manually merge entities.

**Solution:** Build a merge interface that combines entities while preserving all mentions.

**Implementation Notes:**

*Merge workflow:*
```
┌─────────────────────────────────────────────────────┐
│ Merge Entities                                      │
├─────────────────────────────────────────────────────┤
│ Primary Entity: [Robert Mueller    ▼]               │
│                 PERSON • 45 mentions • ●●● 94%      │
│                                                     │
│ Merge Into Primary:                                 │
│ ☑ Bob Mueller (PERSON, 12 mentions, 89%)           │
│ ☑ R. Mueller (PERSON, 3 mentions, 76%)             │
│ ☐ Mueller (PERSON, 8 mentions, 65%)  ← ambiguous   │
│                                                     │
│ After merge:                                        │
│ • Primary keeps canonical name                      │
│ • Merged names become aliases                       │
│ • All mentions transfer to primary                  │
│ • Relationships are combined (duplicates merged)   │
│                                                     │
│ [Preview Changes]  [Cancel]  [Merge Selected]       │
└─────────────────────────────────────────────────────┘
```

*Backend merge logic:*
```python
def merge_entities(primary_id: int, secondary_ids: list[int], user_id: int):
    primary = TrackedEntity.query.get(primary_id)
    
    for sec_id in secondary_ids:
        secondary = TrackedEntity.query.get(sec_id)
        
        # Add secondary name as alias
        add_alias(primary, secondary.name, alias_type='merged')
        
        # Transfer all mentions
        EntityMention.query.filter_by(entity_id=sec_id).update(
            {EntityMention.entity_id: primary_id}
        )
        
        # Merge relationships (complex: handle duplicates)
        merge_relationships(primary_id, sec_id)
        
        # Delete secondary entity
        db.session.delete(secondary)
    
    db.session.commit()
    return primary
```

**Expected Impact:** Users can fix entity fragmentation. Merged entities become more complete and valuable.

---

### Phase 3: Advanced Features (3-6 Months)

*Goal: Intelligence-grade entity resolution and relationship extraction*

---

#### 3.1 Implement Coreference Resolution

**Problem:** Pronouns ("he", "she", "they", "the company") aren't linked to the entities they reference. Sentences like "Mueller said he would investigate" don't connect "he" to "Mueller."

**Solution:** Add coreference resolution to the NLP pipeline.

**Implementation Notes:**

*Recommended: spaCy + neuralcoref or coreferee*
```python
import spacy
import coreferee

nlp = spacy.load('en_core_web_lg')
nlp.add_pipe('coreferee')

def resolve_coreferences(text: str):
    doc = nlp(text)
    
    # Get coreference chains
    resolved_mentions = []
    for chain in doc._.coref_chains:
        # chain[0] is usually the main mention
        main_mention = chain[0]
        for mention in chain[1:]:
            resolved_mentions.append({
                'pronoun': doc[mention.start:mention.end].text,
                'refers_to': doc[main_mention.start:main_mention.end].text,
                'span': (mention.start, mention.end)
            })
    
    return resolved_mentions

# Example:
# "Robert Mueller said he would release the report. The investigator was thorough."
# Returns: 
#   {'pronoun': 'he', 'refers_to': 'Robert Mueller', ...}
#   {'pronoun': 'The investigator', 'refers_to': 'Robert Mueller', ...}
```

*Integration approach:*
1. Run coreference after GLiNER NER
2. For each resolved pronoun, create an EntityMention linked to the resolved entity
3. Mark these mentions as `source='coreference'` for transparency
4. Consider confidence scoring based on distance and context

*Caveats:*
- Coreference resolution is computationally expensive
- Accuracy is ~70-85% even with best models
- Consider running only on high-value documents or on-demand

**Expected Impact:** Relationship extraction becomes more complete. Mentions increase significantly for key entities.

---

#### 3.2 Enhance Relationship Extraction

**Problem:** Current relationship extraction logic is unclear. 10 relationship types exist but population method isn't specified.

**Solution:** Implement explicit relationship extraction using dependency parsing and/or transformer models.

**Implementation Notes:**

*Approach 1: Rule-based with spaCy dependency parsing*
```python
def extract_relationships(doc, entities):
    relationships = []
    
    for sent in doc.sents:
        # Find entities in this sentence
        sent_entities = [e for e in entities if e['start'] >= sent.start and e['end'] <= sent.end]
        
        if len(sent_entities) < 2:
            continue
            
        # Look for relationship indicators
        for token in sent:
            if token.dep_ == 'ROOT' and token.pos_ == 'VERB':
                # Find subject and object
                subj = [c for c in token.children if c.dep_ in ('nsubj', 'nsubjpass')]
                obj = [c for c in token.children if c.dep_ in ('dobj', 'pobj')]
                
                # Map to entities and create relationship
                # ... (simplified)
                relationships.append({
                    'source': subj_entity,
                    'target': obj_entity,
                    'type': classify_relationship(token.lemma_),
                    'confidence': 0.7,
                    'evidence': sent.text
                })
    
    return relationships

def classify_relationship(verb: str) -> str:
    """Map verbs to relationship types."""
    mapping = {
        'work': 'EMPLOYED_BY',
        'own': 'OWNS',
        'acquire': 'ACQUIRED',
        'meet': 'MET_WITH',
        'marry': 'FAMILY',
        # ... expand based on your 10 types
    }
    return mapping.get(verb, 'RELATED_TO')
```

*Approach 2: Transformer-based (higher accuracy, more compute)*
- Consider Rebel (relation extraction) or OpenIE models
- Fine-tune on domain-specific relationships if you have labeled data

*Your 10 relationship types - suggested semantics:*
| Type | Description | Detection Signals |
|------|-------------|-------------------|
| EMPLOYED_BY | Person works at Organization | "works at", "CEO of", "employed by" |
| OWNS | Entity owns another | "owns", "acquired", "purchased" |
| LOCATED_IN | Entity located in Location | "based in", "headquarters in" |
| AFFILIATED_WITH | General association | "member of", "associated with" |
| FAMILY | Family relationship | "married to", "son of", "sister" |
| MET_WITH | Meeting/interaction | "met with", "spoke to", "called" |
| INVESTED_IN | Financial relationship | "invested", "funded", "backed" |
| FOUNDED | Creation relationship | "founded", "started", "created" |
| ACQUIRED | M&A relationship | "acquired", "bought", "merged" |
| RELATED_TO | Catch-all | Co-occurrence in same context |

**Expected Impact:** Relationships become meaningful and queryable. "Show all EMPLOYED_BY relationships" becomes possible.

---

#### 3.3 Knowledge Base Linking

**Problem:** Extracted entities aren't connected to external knowledge. "Apple" could be the company or the fruit—disambiguation requires context.

**Solution:** Link entities to external knowledge bases (Wikidata, DBpedia).

**Implementation Notes:**

*Recommended: spaCy EntityLinker with Wikidata*
```python
import spacy
from spacy.kb import KnowledgeBase

nlp = spacy.load('en_core_web_lg')

# Option 1: Use spacy-entity-linker
# pip install spacy-entity-linker
from spacy.pipeline import EntityLinker
nlp.add_pipe('entityLinker', last=True)

doc = nlp("Apple announced new products")
for ent in doc.ents:
    if hasattr(ent._, 'kb_ents'):
        # Returns Wikidata QIDs with confidence
        print(f"{ent.text} -> {ent._.kb_ents}")  
        # "Apple" -> [(Q312, 0.95)]  # Q312 = Apple Inc.
```

*Benefits of KB linking:*
- Disambiguation: "Apple" → Apple Inc. vs. fruit
- Enrichment: Get descriptions, images, relationships from Wikidata
- Cross-reference: Link to Wikipedia, other databases
- Type refinement: "PERSON" → "Politician", "CEO", "Athlete"

*Integration:*
```python
class TrackedEntity(Base):
    # ... existing fields ...
    wikidata_id = Column(String(20))  # e.g., "Q312"
    wikipedia_url = Column(String(500))
    entity_subtype = Column(String(100))  # e.g., "Politician"
```

**Expected Impact:** Entities gain rich metadata automatically. Disambiguation improves accuracy significantly.

---

#### 3.4 Cross-User Entity Resolution (Optional)

**Problem:** Each user has their own entity silo. The same real-world entity (e.g., "Elon Musk") exists as separate TrackedEntity records for each user.

**Solution:** Introduce a canonical entity layer with user-specific views.

**Implementation Notes:**

*This is complex and may not be needed. Consider if:*
- Multiple users track the same entities
- You want global entity statistics
- You're building collaborative features

*Approach:*
```python
class CanonicalEntity(Base):
    """System-wide entity (not user-specific)."""
    id = Column(Integer, primary_key=True)
    canonical_name = Column(String(255))
    entity_type = Column(String(50))
    wikidata_id = Column(String(20), unique=True)  # Primary key for resolution

class TrackedEntity(Base):
    """User's view of an entity (existing table)."""
    # ... existing fields ...
    canonical_id = Column(Integer, ForeignKey('canonical_entities.id'), nullable=True)
    # If canonical_id is set, this entity is "resolved" to the canonical version
```

*Resolution logic:*
1. When an entity is KB-linked (Phase 3.3), check if canonical entity exists
2. If yes, link TrackedEntity.canonical_id
3. If no, create CanonicalEntity and link
4. UI can show "This entity is also tracked by N other users" (privacy-respecting)

**Expected Impact:** Enables cross-user insights without breaking privacy boundaries. Foundation for collaborative features.

---

#### 3.5 Timeline Visualization

**Problem:** Entity activity over time isn't visualized. Users can't see when entities appeared, peaked, or disappeared.

**Solution:** Add temporal visualization to entity and graph views.

**Implementation Notes:**

*You already have temporal metadata—leverage it:*
```javascript
// Timeline component (using vis-timeline or similar)
const timeline = new vis.Timeline(container, items, options);

// Items from EntityMention.created_at
const items = mentions.map(m => ({
  id: m.id,
  content: m.entity.name,
  start: m.created_at,
  group: m.entity.entity_type
}));
```

*Features:*
- Entity activity timeline (mentions over time)
- Relationship timeline (when relationships were detected)
- Graph animation (show network evolution)
- "Time travel" slider on graph view

**Expected Impact:** Users understand temporal patterns. "This entity was mentioned heavily in March" becomes visible.

---

## Technology Recommendations

### Keep and Expand

| Technology | Current Use | Recommendation |
|------------|-------------|----------------|
| **GLiNER** | NER | Keep—modern and effective |
| **PostgreSQL** | Storage | Keep—schema is solid |
| **NetworkX** | Graph analysis | Keep—expose more to UI |
| **Cytoscape.js** | Export | Expand—full interactive UI |

### Add

| Technology | Purpose | Phase | Complexity |
|------------|---------|-------|------------|
| **RapidFuzz** | Fuzzy matching | 2.1 | Low |
| **spaCy EntityLinker** | KB linking | 3.3 | Medium |
| **coreferee** | Coreference | 3.1 | Medium |
| **cose-bilkent** | Cytoscape layout | 2.3 | Low |

### Consider (Not Required)

| Technology | Purpose | When to Consider |
|------------|---------|------------------|
| **Dedupe** | Advanced entity resolution | If fuzzy matching insufficient |
| **Senzing** | Enterprise-scale resolution | 100K+ entities |
| **G6/Graphin** | Alternative to Cytoscape | If Cytoscape proves limiting |
| **KeyLines/ReGraph** | Commercial graph viz | If budget allows and scale demands |

### Avoid

| Technology | Reason |
|------------|--------|
| **Neo4j** | Overkill for current scale; PostgreSQL + NetworkX sufficient |
| **Custom ML models** | Pre-trained models (spaCy, GLiNER) are sufficient initially |
| **Real-time streaming** | Batch processing is fine for current use case |

---

## Recommended Next Steps

### Immediate (This Week)

1. **Audit current relationship extraction:** Document how EntityRelationship records are currently created. This is a critical unknown.

2. **Add confidence display:** Quick win—add confidence badges to entity UI. 2-4 hours of work.

3. **Test Cytoscape.js graph:** Take existing export, render it client-side. Evaluate performance with real data.

### Short-Term (Next 2 Weeks)

4. **Design entity card component:** Mockup the expanded entity card UI. Get user feedback before building.

5. **Implement fuzzy matching POC:** Add RapidFuzz, test with existing entities. Measure duplicate detection rate.

6. **Define alias schema:** Add EntityAlias table. Start with manual alias entry.

### Medium-Term (Month 1-2)

7. **Build interactive graph view:** Full Cytoscape.js integration with filtering and expansion.

8. **Deploy fuzzy matching:** Integrate into entity creation flow with merge suggestions.

9. **Implement entity merge UI:** Allow users to manually merge entities.

### Quarterly Planning

10. **Evaluate coreference resolution:** Test accuracy and performance. Decide if value justifies compute cost.

11. **Pilot KB linking:** Start with organizations (easiest to disambiguate).

12. **Gather user feedback:** After Phase 2, assess what's most needed for Phase 3.

---

## Glossary

For developers new to entity systems:

| Term | Definition |
|------|------------|
| **NER** | Named Entity Recognition—identifying entities (people, organizations, locations) in text |
| **Entity Resolution** | Determining when different mentions refer to the same real-world entity |
| **Coreference Resolution** | Linking pronouns ("he", "they") to the entities they reference |
| **Knowledge Base (KB)** | External database of entities (Wikidata, DBpedia) with structured information |
| **Fuzzy Matching** | Matching strings that are similar but not identical ("Bob" ≈ "Robert") |
| **Centrality** | Graph metric measuring how "important" or connected a node is |
| **Betweenness** | Graph metric measuring how often a node lies on paths between other nodes |
| **Community Detection** | Algorithm to find clusters of densely connected nodes |
| **Hairball Problem** | Graph visualization issue where too many nodes/edges create an unreadable mess |
| **Progressive Disclosure** | UI pattern showing minimal info initially, with more available on demand |

---

*Document created: January 2025*  
*For: The-Pulse Development Team*
