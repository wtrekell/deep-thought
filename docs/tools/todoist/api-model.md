# Todoist API Model

Module: `todoist_api_python.models`

## Table of Contents

- [Type Aliases](#type-aliases)
- [Attachment](#attachment)
- [AuthResult](#authresult)
- [Collaborator](#collaborator)
- [Comment](#comment)
- [Deadline](#deadline)
- [Due](#due)
- [Duration](#duration)
- [Label](#label)
- [Meta](#meta)
- [Project](#project)
- [Section](#section)
- [Task](#task)

## Type Aliases

| Name | Symbol |
| --- | --- |
| `ApiDate` | attribute |
| `ApiDue` | attribute |
| `DurationUnit` | attribute |
| `ViewStyle` | attribute |

## Attachment

| Attribute | |
| --- | --- |
| `file_duration` | |
| `file_name` | |
| `file_size` | |
| `file_type` | |
| `file_url` | |
| `image` | |
| `image_height` | |
| `image_width` | |
| `resource_type` | |
| `title` | |
| `upload_state` | |
| `url` | |

## AuthResult

| Attribute | |
| --- | --- |
| `access_token` | |
| `state` | |

## Collaborator

| Attribute | |
| --- | --- |
| `email` | |
| `id` | |
| `name` | |

## Comment

| Attribute | |
| --- | --- |
| `attachment` | |
| `content` | |
| `id` | |
| `posted_at` | |
| `poster_id` | |
| `project_id` | |
| `task_id` | |

## Deadline

| Attribute | |
| --- | --- |
| `date` | |
| `lang` | |

## Due

| Attribute | |
| --- | --- |
| `date` | |
| `is_recurring` | |
| `lang` | |
| `string` | |
| `timezone` | |

## Duration

| Attribute | |
| --- | --- |
| `amount` | |
| `unit` | |

## Label

| Attribute | |
| --- | --- |
| `color` | |
| `id` | |
| `is_favorite` | |
| `name` | |
| `order` | |

## Meta

| Attribute | |
| --- | --- |
| `assignee` | |
| `deadline` | |
| `due` | |
| `labels` | |
| `project` | |
| `section` | |

## Project

| Attribute | |
| --- | --- |
| `can_assign_tasks` | |
| `color` | |
| `created_at` | |
| `description` | |
| `folder_id` | |
| `id` | |
| `is_archived` | |
| `is_collapsed` | |
| `is_favorite` | |
| `is_inbox_project` | |
| `is_shared` | |
| `name` | |
| `order` | |
| `parent_id` | |
| `updated_at` | |
| `url` | |
| `view_style` | |
| `workspace_id` | |

## Section

| Attribute | |
| --- | --- |
| `id` | |
| `is_collapsed` | |
| `name` | |
| `order` | |
| `project_id` | |

## Task

| Attribute | |
| --- | --- |
| `assignee_id` | |
| `assigner_id` | |
| `completed_at` | |
| `content` | |
| `created_at` | |
| `creator_id` | |
| `deadline` | |
| `description` | |
| `due` | |
| `duration` | |
| `id` | |
| `is_collapsed` | |
| `is_completed` | |
| `labels` | |
| `meta` | |
| `order` | |
| `parent_id` | |
| `priority` | |
| `project_id` | |
| `section_id` | |
| `updated_at` | |
| `url` | |
