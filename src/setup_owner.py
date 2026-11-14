"""Interactive first-time setup for Neha's local owner account."""
import getpass

try:
    from .local_owner_auth import LocalOwnerAuth, OwnerAccountError
except ImportError:
    from local_owner_auth import LocalOwnerAuth, OwnerAccountError


def main():
    auth = LocalOwnerAuth()
    if auth.is_configured():
        try:
            auth._read_record()
        except OwnerAccountError:
            print(
                "An owner account file exists but is unreadable. "
                "It has been preserved; restore a verified backup or repair "
                "the file before running setup again."
            )
            return 1
        print("A Neha owner account already exists. Setup will not overwrite it.")
        return 1

    username = input("Choose Neha owner username: ").strip()
    password = getpass.getpass("Choose a Neha-only password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm Neha-only password: ")
    if password != confirmation:
        print("Passwords do not match.")
        return 1
    try:
        account = auth.setup(username, password)
    except OwnerAccountError as exc:
        print("Setup failed:", exc)
        return 1
    finally:
        del password
        del confirmation

    print("Neha owner account created.")
    print("Username:", account["username"])
    print("Owner ID:", account["owner_id"])
    print("Password is not displayed or stored in plain text.")
    print("Keep data/owner_auth.json private; the repository ignores data/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
