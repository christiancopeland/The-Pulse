from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from uuid import UUID
from pydantic import BaseModel
from sqlalchemy import select, text, update, func
import logging

from ....database import get_db
from ....core.dependencies import get_local_user, LocalUser
from ....services.entity_tracker import EntityTrackingService
from ....services.document_processor import DocumentProcessor
from ....models.entities import TrackedEntity, EntityMention

router = APIRouter()
document_processor = DocumentProcessor()
logger = logging.getLogger(__name__)


class EntityTrackRequest(BaseModel):
    name: str
    entity_type: str = "CUSTOM"
    metadata: Optional[Dict] = None


@router.post("/track")
async def track_entity(
    entity: EntityTrackRequest,
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """Add a new entity to track"""
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id
    )
    try:
        tracked_entity = await entity_tracker.add_tracked_entity(
            name=entity.name,
            entity_type=entity.entity_type,
            metadata=entity.metadata,
            user_id=current_user.user_id
        )
        return tracked_entity
    except Exception as e:
        logger.error(f"Error tracking entity: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
    
@router.delete("/{entity_name}")
async def delete_entity(
    entity_name: str,
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """Delete a tracked entity"""
    try:
        # Find the entity
        query = select(TrackedEntity).where(
            TrackedEntity.name_lower == entity_name.lower(),
            TrackedEntity.user_id == current_user.user_id
        )
        result = await session.execute(query)
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{entity_name}' not found"
            )
        
        # Delete related mentions first (if your DB doesn't handle cascading deletes)
        delete_mentions = text("""
            DELETE FROM entity_mentions 
            WHERE entity_id = :entity_id
        """)
        await session.execute(delete_mentions, {"entity_id": entity.entity_id})
        
        # Delete the entity
        await session.delete(entity)
        await session.commit()
        
        return {"status": "success", "message": f"Entity '{entity_name}' deleted"}
        
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete entity: {str(e)}"
        )


@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Search entities by name with fuzzy matching.

    Uses ILIKE for substring matching and orders by relevance.
    Prioritizes exact matches, then prefix matches, then substring matches.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum results to return
        entity_type: Optional filter by type (person, org, location)

    Returns:
        List of matching entities with relevance scores
    """
    try:
        search_lower = q.lower()

        # Build query with relevance scoring
        # Using CASE to prioritize: exact > prefix > contains
        query = text("""
            SELECT
                entity_id,
                name,
                entity_type,
                entity_metadata,
                created_at,
                CASE
                    WHEN LOWER(name) = :exact THEN 3
                    WHEN LOWER(name) LIKE :prefix THEN 2
                    ELSE 1
                END as relevance
            FROM tracked_entities
            WHERE user_id = :user_id
              AND LOWER(name) LIKE :pattern
              {type_filter}
            ORDER BY relevance DESC, name ASC
            LIMIT :limit
        """.format(
            type_filter="AND LOWER(entity_type) = :entity_type" if entity_type else ""
        ))

        params = {
            "user_id": str(current_user.user_id),
            "exact": search_lower,
            "prefix": f"{search_lower}%",
            "pattern": f"%{search_lower}%",
            "limit": limit
        }
        if entity_type:
            params["entity_type"] = entity_type.lower()

        result = await session.execute(query, params)
        rows = result.fetchall()

        entities = [
            {
                "entity_id": str(row.entity_id),
                "name": row.name,
                "entity_type": row.entity_type,
                "entity_metadata": row.entity_metadata,
                "relevance": row.relevance
            }
            for row in rows
        ]

        return {
            "results": entities,
            "count": len(entities),
            "query": q
        }

    except Exception as e:
        logger.error(f"Entity search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/{entity_name}/mentions")
async def get_entity_mentions(
    entity_name: str,
    limit: int = 50,
    offset: int = 0,
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """Get mentions for an entity"""
    logger.debug(f"Getting mentions for entity: {entity_name}")
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id
    )
    try:
        mentions = await entity_tracker.get_entity_mentions(
            entity_name=entity_name,
            limit=limit,
            offset=offset
        )
        # BUG-002 FIX: Wrap response in object with mentions key
        return {"mentions": mentions, "total": len(mentions)}
    except Exception as e:
        logger.error(f"Error getting mentions for {entity_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("")
async def get_tracked_entities(
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("mentions", description="Sort by: mentions, name, recent"),
    type: Optional[str] = Query(None, description="Filter by entity type")
) -> dict:
    """
    Get tracked entities for the current user with mention counts.

    Args:
        limit: Maximum number of entities to return
        offset: Number of entities to skip
        sort: Sort order (mentions, name, recent)
        type: Filter by entity type (person, org, location)

    Returns:
        Dict with entities list and total count
    """
    try:
        # Base query with mention count
        base_query = (
            select(
                TrackedEntity,
                func.count(EntityMention.mention_id).label('mention_count')
            )
            .outerjoin(EntityMention, TrackedEntity.entity_id == EntityMention.entity_id)
            .where(TrackedEntity.user_id == current_user.user_id)
        )

        # Apply type filter
        if type:
            base_query = base_query.where(
                func.lower(TrackedEntity.entity_type) == type.lower()
            )

        # Group by entity
        base_query = base_query.group_by(TrackedEntity.entity_id)

        # Apply sorting
        if sort == "name":
            base_query = base_query.order_by(TrackedEntity.name.asc())
        elif sort == "recent":
            base_query = base_query.order_by(TrackedEntity.created_at.desc())
        else:  # Default: mentions
            base_query = base_query.order_by(func.count(EntityMention.mention_id).desc())

        # Get total count (without pagination)
        count_query = (
            select(func.count(TrackedEntity.entity_id))
            .where(TrackedEntity.user_id == current_user.user_id)
        )
        if type:
            count_query = count_query.where(
                func.lower(TrackedEntity.entity_type) == type.lower()
            )
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = base_query.offset(offset).limit(limit)

        result = await session.execute(query)
        rows = result.all()

        entities = [
            {
                "entity_id": str(row.TrackedEntity.entity_id),
                "name": row.TrackedEntity.name,
                "entity_type": row.TrackedEntity.entity_type,
                "created_at": str(row.TrackedEntity.created_at),
                "entity_metadata": row.TrackedEntity.entity_metadata,
                "mention_count": row.mention_count or 0
            }
            for row in rows
        ]

        return {
            "entities": entities,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Failed to fetch tracked entities: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tracked entities: {str(e)}"
        )


class BulkDeleteRequest(BaseModel):
    entity_ids: List[str]


@router.delete("/bulk")
async def bulk_delete_entities(
    request: BulkDeleteRequest,
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Delete multiple entities at once.

    Args:
        entity_ids: List of entity IDs to delete

    Returns:
        Number of entities deleted
    """
    try:
        if not request.entity_ids:
            raise HTTPException(400, "No entity IDs provided")

        deleted_count = 0

        for entity_id_str in request.entity_ids:
            try:
                entity_id = UUID(entity_id_str)
            except ValueError:
                logger.warning(f"Invalid entity ID: {entity_id_str}")
                continue

            # Find the entity
            query = select(TrackedEntity).where(
                TrackedEntity.entity_id == entity_id,
                TrackedEntity.user_id == current_user.user_id
            )
            result = await session.execute(query)
            entity = result.scalar_one_or_none()

            if not entity:
                logger.warning(f"Entity not found or not owned by user: {entity_id}")
                continue

            # Delete related mentions first
            delete_mentions = text("""
                DELETE FROM entity_mentions
                WHERE entity_id = :entity_id
            """)
            await session.execute(delete_mentions, {"entity_id": str(entity_id)})

            # Delete the entity
            await session.delete(entity)
            deleted_count += 1

        await session.commit()

        logger.info(f"Bulk deleted {deleted_count} entities for user {current_user.user_id}")

        return {
            "status": "success",
            "deleted": deleted_count,
            "requested": len(request.entity_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Bulk delete failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete entities: {str(e)}"
        )

@router.get("/{entity_name}/relationships")
async def get_entity_relationships(
    entity_name: str,
    include_news: bool = True,
    include_docs: bool = True,
    min_shared: int = 1,
    debug: bool = False,
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """Get relationship network for an entity"""
    logger.debug(f"Getting relationships for entity: {entity_name}")
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id,
        debug=debug
    )
    try:
        # First check if we have any mentions for this entity
        mentions_check = await session.execute(
            text("""
                SELECT COUNT(*) 
                FROM entity_mentions em
                JOIN tracked_entities te ON em.entity_id = te.entity_id
                WHERE te.name_lower = :entity_name
            """),
            {"entity_name": entity_name.lower()}
        )
        mention_count = mentions_check.scalar()
        
        if mention_count == 0:
            logger.debug(f"No mentions found for {entity_name}, triggering scan...")
            # Get entity details
            entity = await session.execute(
                select(TrackedEntity)
                .where(TrackedEntity.name_lower == entity_name.lower())
            )
            entity = entity.scalar_one()
            
            # Scan for mentions
            await entity_tracker._scan_existing_documents(entity)
        
        # Now analyze relationships
        network = await entity_tracker.analyze_entity_relationships(
            entity_name=entity_name
        )
        return network
        
    except Exception as e:
        logger.error(f"Error getting relationships for {entity_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{entity_name}/scan")
async def scan_entity_mentions(
    entity_name: str,
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db)
):
    """Manually trigger a scan for entity mentions"""
    logger.debug(f"Starting scan for entity: {entity_name}")
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id
    )
    try:
        # Get entity details
        entity = await session.execute(
            select(TrackedEntity)
            .where(TrackedEntity.name_lower == entity_name.lower())
        )
        entity = entity.scalar_one()
        logger.debug(f"Found entity: {entity.name} (ID: {entity.entity_id})")
        
        # Scan for mentions
        mentions_added = await entity_tracker._scan_existing_documents(entity)
        
        return {
            "status": "success",
            "mentions_found": mentions_added,
            "message": f"Successfully scanned for mentions of '{entity_name}'"
        }
    except Exception as e:
        logger.error(f"Error scanning for {entity_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/diagnostic")
async def diagnostic_check(
    session: AsyncSession = Depends(get_db)
):
    """Check database state for troubleshooting"""
    try:
        # Check news articles
        news_query = text("SELECT COUNT(*) as count, COUNT(CASE WHEN content IS NOT NULL THEN 1 END) as with_content FROM news_articles")
        news_result = await session.execute(news_query)
        news_stats = news_result.first()
        
        # Check tracked entities
        entity_query = text("SELECT COUNT(*) FROM tracked_entities")
        entity_result = await session.execute(entity_query)
        entity_count = entity_result.scalar()
        
        # Check mentions
        mention_query = text("SELECT COUNT(*) FROM entity_mentions")
        mention_result = await session.execute(mention_query)
        mention_count = mention_result.scalar()
        
        return {
            "news_articles": {
                "total": news_stats.count,
                "with_content": news_stats.with_content
            },
            "tracked_entities": entity_count,
            "entity_mentions": mention_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Diagnostic check failed: {str(e)}"
        )

@router.get("/diagnostic/articles")
async def diagnostic_check_articles(
    limit: int = 5,
    session: AsyncSession = Depends(get_db)
):
    """Check sample of articles for troubleshooting"""
    try:
        # Get sample of articles with their content status
        article_query = text("""
            SELECT 
                id,
                title,
                url,
                scraped_at,
                CASE 
                    WHEN content IS NULL THEN 'missing'
                    WHEN content = '' THEN 'empty'
                    ELSE 'present'
                END as content_status,
                CASE 
                    WHEN content IS NOT NULL THEN length(content)
                    ELSE 0
                END as content_length
            FROM news_articles
            ORDER BY scraped_at DESC
            LIMIT :limit
        """)
        
        result = await session.execute(article_query, {"limit": limit})
        articles = result.fetchall()
        
        return {
            "articles": [
                {
                    "id": str(article.id),
                    "title": article.title,
                    "url": article.url,
                    "scraped_at": str(article.scraped_at),
                    "content_status": article.content_status,
                    "content_length": article.content_length
                }
                for article in articles
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Article diagnostic check failed: {str(e)}"
        )


@router.get("/duplicates")
async def find_duplicate_entities(
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Find entities that may be duplicates based on WikiData QID.

    Returns groups of entities that share the same WikiData QID,
    indicating they represent the same real-world entity.

    Args:
        limit: Maximum number of duplicate groups to return

    Returns:
        List of duplicate groups with entity details
    """
    try:
        # Find entities with duplicate WikiData QIDs
        query = text("""
            SELECT
                entity_metadata->>'wikidata_id' as wikidata_id,
                COUNT(*) as count,
                ARRAY_AGG(name ORDER BY created_at) as names,
                ARRAY_AGG(entity_id::text ORDER BY created_at) as entity_ids,
                ARRAY_AGG(entity_type ORDER BY created_at) as entity_types
            FROM tracked_entities
            WHERE user_id = :user_id
              AND entity_metadata->>'wikidata_id' IS NOT NULL
            GROUP BY entity_metadata->>'wikidata_id'
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT :limit
        """)

        result = await session.execute(query, {
            "user_id": str(current_user.user_id),
            "limit": limit
        })

        duplicates = []
        for row in result.fetchall():
            duplicates.append({
                "wikidata_id": row.wikidata_id,
                "count": row.count,
                "names": row.names,
                "entity_ids": row.entity_ids,
                "entity_types": row.entity_types,
            })

        return {
            "duplicates": duplicates,
            "total_groups": len(duplicates),
            "message": f"Found {len(duplicates)} groups of duplicate entities"
        }

    except Exception as e:
        logger.error(f"Failed to find duplicates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to find duplicate entities: {str(e)}"
        )


@router.post("/merge")
async def merge_entities(
    primary_id: UUID = Query(..., description="Entity ID to keep (primary)"),
    secondary_id: UUID = Query(..., description="Entity ID to merge into primary"),
    current_user: LocalUser = Depends(get_local_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Merge a secondary entity into a primary entity.

    - Moves all mentions from secondary to primary
    - Merges aliases into primary's metadata
    - Deletes the secondary entity

    Args:
        primary_id: Entity to keep
        secondary_id: Entity to merge and delete

    Returns:
        Merge result with details
    """
    try:
        # Verify both entities exist and belong to user
        primary_result = await session.execute(
            select(TrackedEntity).where(
                TrackedEntity.entity_id == primary_id,
                TrackedEntity.user_id == current_user.user_id
            )
        )
        primary = primary_result.scalar_one_or_none()

        secondary_result = await session.execute(
            select(TrackedEntity).where(
                TrackedEntity.entity_id == secondary_id,
                TrackedEntity.user_id == current_user.user_id
            )
        )
        secondary = secondary_result.scalar_one_or_none()

        if not primary:
            raise HTTPException(404, f"Primary entity not found: {primary_id}")
        if not secondary:
            raise HTTPException(404, f"Secondary entity not found: {secondary_id}")
        if primary_id == secondary_id:
            raise HTTPException(400, "Cannot merge entity with itself")

        # Count mentions being moved
        mention_count_query = select(EntityMention).where(
            EntityMention.entity_id == secondary_id
        )
        mention_result = await session.execute(mention_count_query)
        mentions_to_move = len(list(mention_result.scalars().all()))

        # Move all mentions from secondary to primary
        await session.execute(
            update(EntityMention)
            .where(EntityMention.entity_id == secondary_id)
            .values(entity_id=primary_id)
        )

        # Merge aliases into primary's metadata
        primary_metadata = dict(primary.entity_metadata) if primary.entity_metadata else {}
        secondary_metadata = dict(secondary.entity_metadata) if secondary.entity_metadata else {}

        primary_aliases = set(primary_metadata.get("aliases", []))
        secondary_aliases = set(secondary_metadata.get("aliases", []))
        secondary_aliases.add(secondary.name)  # Add secondary's name as alias

        merged_aliases = list(primary_aliases | secondary_aliases)

        # Track merge history
        merge_history = primary_metadata.get("merged_from", [])
        merge_history.append({
            "entity_id": str(secondary_id),
            "name": secondary.name,
            "merged_at": str(uuid.uuid1().time)  # Timestamp
        })

        primary_metadata["aliases"] = merged_aliases
        primary_metadata["merged_from"] = merge_history

        # Update primary entity metadata
        primary.entity_metadata = primary_metadata

        # Delete secondary entity
        await session.delete(secondary)
        await session.commit()

        logger.info(
            f"Merged entity {secondary.name} ({secondary_id}) into "
            f"{primary.name} ({primary_id}), moved {mentions_to_move} mentions"
        )

        return {
            "status": "merged",
            "primary": {
                "entity_id": str(primary_id),
                "name": primary.name,
            },
            "secondary": {
                "entity_id": str(secondary_id),
                "name": secondary.name,
            },
            "mentions_moved": mentions_to_move,
            "aliases_merged": merged_aliases,
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to merge entities: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to merge entities: {str(e)}"
        )
