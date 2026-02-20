# Reusable file search

A Python script that audits [Hugo `readfile` shortcode](https://gohugo.io/content-management/shortcodes/) usage across a content directory. It finds every reusable Markdown file, counts how many times each one is referenced, and optionally performs cleanup actions such as inlining single-use files or deleting unused ones.

## Requirements

Python 3.9 or later. No third-party packages required.

## Usage

```sh
python reusable_file_search.py <reusable_dir> <content_dir> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `reusable_dir` | Directory containing reusable Markdown files, e.g. `content/reusable/md/`. |
| `content_dir` | Directory containing content Markdown files that use `readfile` shortcodes. |
| `--show-locations` | Show which content files reference each reusable file. |
| `--show-missing` | List reusable files referenced in content but not found on disk. |
| `--inline-singles` | For each reusable file used exactly once, replace its `readfile` shortcode with the file's content, then delete the reusable file. |
| `--delete-unused` | Delete reusable Markdown files that are not referenced in any content file. |

## How it works

The script searches every `.md` file inside `content_dir` (including subdirectories) for Hugo `readfile` shortcodes in the form:

```md
{{< readfile file="content/reusable/md/some_file.md" >}}
```

It then matches the path in each shortcode against the Markdown files found in `reusable_dir`. A file is considered matched if the shortcode path is a suffix of the reusable file's path, or if the filenames match as a fallback.

### Example directory structure

```
my-hugo-site/
├── content/
│   ├── reusable/
│   │   └── md/
│   │       ├── windows_spaces_and_directories.md
│   │       ├── windows_top_level_directory_names.md
│   │       └── install_note.md
│   ├── docs/
│   │   ├── windows-setup.md
│   │   └── getting-started.md
│   └── guides/
│       └── advanced.md
```

In this layout you would run:

```sh
python reusable_file_search.py \
  content/reusable/md/ \
  content/
```

### Example shortcode usage

A content file such as `content/docs/windows-setup.md` might reference two reusable files:

```md
## Spaces and Directories

{{< readfile file="content/reusable/md/windows_spaces_and_directories.md" >}}

## Top-level Directory Names

{{< readfile file="content/reusable/md/windows_top_level_directory_names.md" >}}
```

## Example output

Running the script without any optional flags prints a usage summary:

```
Reusable file audit — 3 file(s) found

============================================================

[ALERT] 1 file(s) used 0 or 1 time(s):

  [!] content/reusable/md/install_note.md  (0 uses)

File                                                     Uses
--------------------------------------------------------------
  content/reusable/md/windows_spaces_and_directories.md    4
  content/reusable/md/windows_top_level_directory_names.md 2
  content/reusable/md/install_note.md                      0
```

### `--show-locations`

Lists every content file that references each reusable file:

```sh
python reusable_file_search.py content/reusable/md/ content/ --show-locations
```

```
File                                                     Uses
--------------------------------------------------------------
  content/reusable/md/windows_spaces_and_directories.md    4
      -> content/docs/windows-setup.md
      -> content/docs/getting-started.md
      -> content/guides/advanced.md
      -> content/guides/quick-start.md
```

### `--show-missing`

Reports any `readfile` paths referenced in content files that do not correspond to a file in `reusable_dir`:

```sh
python reusable_file_search.py content/reusable/md/ content/ --show-missing
```

```
[MISSING] 1 referenced file(s) not found on disk:

  [?] content/reusable/md/deleted_file.md
```

Each missing path is reported only once, even if it is referenced in multiple content files.

### `--inline-singles`

For each reusable file that appears in exactly one content file, the shortcode is replaced with the file's content and the reusable file is deleted:

```sh
python reusable_file_search.py content/reusable/md/ content/ --inline-singles
```

```
[INLINE] Inlining 1 file(s) used exactly once:

  [OK]   content/reusable/md/install_note.md
         inlined into: content/docs/getting-started.md
         Reusable file deleted.
```

### `--delete-unused`

Deletes every reusable Markdown file that has zero references in the content directory:

```sh
python reusable_file_search.py content/reusable/md/ content/ --delete-unused
```

```
[DELETE-UNUSED] Deleting 1 unused file(s):

  [OK]   Deleted: content/reusable/md/install_note.md
```

Flags can be combined, for example to inline single-use files and delete unused ones in one pass:

```sh
python reusable_file_search.py content/reusable/md/ content/ --inline-singles --delete-unused
```

## Tests

Run the test suite with:

```sh
python -m pytest test_reusable_file_search.py -v
```


