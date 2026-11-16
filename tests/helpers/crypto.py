from rayohx import EncryptionInfo, EncryptionMethod, Segment
from tests.helpers.media import BASE, IV

DATA = b"The quick brown fox jumps over the lazy dog" * 10


ENCRYPTION = EncryptionInfo(EncryptionMethod.AES_128, BASE + "key.bin", IV)


def segment(sequence: int = 5, encryption: EncryptionInfo | None = ENCRYPTION) -> Segment:
    return Segment(
        index=0, uri=BASE + "a.ts", duration=4, sequence_number=sequence, encryption=encryption
    )
