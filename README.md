# FastPart — camera-ready best partitions (Titan23, ε = 2 %, K = 2/3/4)

This repository holds the partitions produced by an improved to-be-released FastPart solver
(developed under the internal codename **CORD**) on the 22 Titan23 designs at ε = 2 %
for K = 2, 3 and 4 — 66 cells in total. Benchmarks are not redistributed here; only the
resulting assignments. For the actual FastPart solver which appeared at ICCAD 2026, see the src branch called iccad26-camera-ready in this same repo (that branch should replicate results in the paper, while the cuts in the main branch are better than what the paper reports).

CORD is under active development and iteration, and will be hopefully released soon. 

Every cut in the table below was re-scored, immediately before publication, by the
independent golden evaluator directly from the `.part` file shipped in
`best-partitions/` — 66 of 66 verified, zero mismatches. The fourth column is the target
these runs were chasing: **min(KEP, FastPart-original)**, the best value previously
attained by either the KEP solver or the original FastPart.

## Result

| | WIN (below target) | TIE (equal) | above target | geomean cut / target |
|---|---:|---:|---:|---:|
| **All 66 cells** | **30** | **35** | **1** | **0.9941** |
| K = 2 | 3 | 19 | 0 | 0.9994 |
| K = 3 | 12 | 10 | 0 | 0.9925 |
| K = 4 | 15 | 6 | 1 | 0.9905 |

65 of 66 cells meet or beat the target; the geometric mean cut is 0.59 % below it.
The single exception is `gsm_switch` K = 4.

## Balance convention

Two-sided, absolute. For a hypergraph of total vertex weight *W*, every block *b* satisfies

    ceil((1/K − ε/100)·W)  ≤  w_b  ≤  floor((1/K + ε/100)·W)

so at K = 4, ε = 2 % each block holds between 23 % and 27 % of the weight. The objective is
**cut-net** (each hyperedge spanning more than one block counts once, times its weight).
Every partition below is legal under this convention.

## Files

`best-partitions/<instance>.k<K>.part.gz` — gzip of a plain text file with one block index
per line, in vertex order, 0-based, `n` lines for `n` vertices.

    gunzip -c best-partitions/directrf.k2.part.gz | head

## Results table

Cut = the value achieved by these partitions. Target = min(KEP, FastPart-original).

| Instance | K | Cut (FastPart camera-ready) | Target = min(KEP, FastPart-original) |
| --- | ---: | ---: | ---: |
| LU230 | 2 | 3265 | 3277 |
| LU230 | 3 | 4391 | 4484 |
| LU230 | 4 | 5315 | 5444 |
| LU_Network | 2 | 524 | 524 |
| LU_Network | 3 | 784 | 784 |
| LU_Network | 4 | 1351 | 1352 |
| SLAM_spheric | 2 | 1061 | 1061 |
| SLAM_spheric | 3 | 2644 | 2684 |
| SLAM_spheric | 4 | 3117 | 3137 |
| bitcoin_miner | 2 | 1489 | 1489 |
| bitcoin_miner | 3 | 1806 | 1831 |
| bitcoin_miner | 4 | 1830 | 1831 |
| bitonic_mesh | 2 | 581 | 581 |
| bitonic_mesh | 3 | 889 | 895 |
| bitonic_mesh | 4 | 1085 | 1087 |
| cholesky_bdti | 2 | 1156 | 1156 |
| cholesky_bdti | 3 | 1647 | 1665 |
| cholesky_bdti | 4 | 1844 | 1844 |
| cholesky_mc | 2 | 282 | 282 |
| cholesky_mc | 3 | 787 | 787 |
| cholesky_mc | 4 | 975 | 975 |
| dart | 2 | 784 | 784 |
| dart | 3 | 1070 | 1083 |
| dart | 4 | 1244 | 1279 |
| denoise | 2 | 416 | 416 |
| denoise | 3 | 715 | 720 |
| denoise | 4 | 843 | 847 |
| des90 | 2 | 371 | 371 |
| des90 | 3 | 504 | 504 |
| des90 | 4 | 654 | 656 |
| directrf | 2 | 490 | 490 |
| directrf | 3 | 711 | 711 |
| directrf | 4 | 1027 | 1030 |
| gsm_switch | 2 | 1479 | 1479 |
| gsm_switch | 3 | 2324 | 2345 |
| gsm_switch | 4 | 2781 | 2751 |
| mes_noc | 2 | 633 | 633 |
| mes_noc | 3 | 1094 | 1105 |
| mes_noc | 4 | 1306 | 1306 |
| minres | 2 | 207 | 207 |
| minres | 3 | 309 | 309 |
| minres | 4 | 405 | 405 |
| neuron | 2 | 243 | 243 |
| neuron | 3 | 362 | 362 |
| neuron | 4 | 405 | 405 |
| openCV | 2 | 428 | 432 |
| openCV | 3 | 492 | 492 |
| openCV | 4 | 508 | 515 |
| segmentation | 2 | 107 | 107 |
| segmentation | 3 | 447 | 447 |
| segmentation | 4 | 479 | 479 |
| sparcT1_chip2 | 2 | 873 | 874 |
| sparcT1_chip2 | 3 | 1256 | 1297 |
| sparcT1_chip2 | 4 | 1480 | 1531 |
| sparcT1_core | 2 | 974 | 974 |
| sparcT1_core | 3 | 1717 | 1762 |
| sparcT1_core | 4 | 2162 | 2174 |
| sparcT2_core | 2 | 1183 | 1183 |
| sparcT2_core | 3 | 2053 | 2059 |
| sparcT2_core | 4 | 2777 | 2851 |
| stap_qrd | 2 | 370 | 370 |
| stap_qrd | 3 | 462 | 462 |
| stap_qrd | 4 | 633 | 675 |
| stereo_vision | 2 | 169 | 169 |
| stereo_vision | 3 | 320 | 320 |
| stereo_vision | 4 | 370 | 372 |

## Verification

Score any file against its benchmark with the cut-net objective and check the two-sided
window above. SHA-256 of each uncompressed `.part` payload:

| File | SHA-256 (uncompressed) |
| --- | --- |
| LU230.k2.part.gz | `ceb9f66f8ba5a47dd64d995a49d246f50e40fc40750757bdebb412ea5e6778de` |
| LU230.k3.part.gz | `3409eeec7fd1af109d9106bc3bd4a4e401ed1afbd421a8191c9b9c5523f14902` |
| LU230.k4.part.gz | `599c03580a94636972cf4fa3b43f21de25baf9164ce3a39745b8cc42e38a5820` |
| LU_Network.k2.part.gz | `961d5aba067390eeb5692290a57bf08d83832b6a879f425a189f30e8a895071c` |
| LU_Network.k3.part.gz | `b96074bd5c8b282e298e2989a85d39a91367702eb090255c4d184a721bf18b7e` |
| LU_Network.k4.part.gz | `ba3cbce3b288f2964d861804c3df3d1b384d2c130b2438864d414ce328e1a947` |
| SLAM_spheric.k2.part.gz | `0843585c00d2484a4f7d2974113940bcd0603c49cf2137c187cdd1ffd46e2450` |
| SLAM_spheric.k3.part.gz | `fedf6d720933cf647b0823b6bf14fafd21db2c534b65abe6aaf65aef1d2c9844` |
| SLAM_spheric.k4.part.gz | `da96e8152b9ebb4eb21d5af61deffed2ea995c676cb0a06e034688dea9d2e4b3` |
| bitcoin_miner.k2.part.gz | `1b8027ccc0ca7b19456a1198c8c3fe7c24729001f1d6c5191e8d186193d06cdd` |
| bitcoin_miner.k3.part.gz | `c57514add8484ea13314de7072773481ecb22198811519fa18fb290759b54438` |
| bitcoin_miner.k4.part.gz | `f1e33c73d3d38deef6f633a0eeca1b2d9982d8bafab2d9387badc841fafe179d` |
| bitonic_mesh.k2.part.gz | `55e9a467087a237a95868d7ef98eb105ed4da4bb3f4f6506a099ceb835c26b87` |
| bitonic_mesh.k3.part.gz | `f673e602b512f2baccacd6f06312d8f48e521b06c54b02ab28d2cc059c0ce7d0` |
| bitonic_mesh.k4.part.gz | `f7cc497b7e7010303ba26d20ddcb46bdabac3c22d676468a77e1516e56774758` |
| cholesky_bdti.k2.part.gz | `d669c8d52473025dc96ac5b8b4f3e6222851d0c314b8c0143ff811ecb351fe46` |
| cholesky_bdti.k3.part.gz | `8c2f508c0f7a8180514c1bf7efb63e88de023e5fe10f57a8a0ef413555af65d7` |
| cholesky_bdti.k4.part.gz | `b0ddd1a590b334f5605e903b6dad6f3be2aed88d4314d3e9d931f8e3f18cfbea` |
| cholesky_mc.k2.part.gz | `265d42f3a4d63c534a6ff18b572c44e48320727332d17ac154c65d7974139261` |
| cholesky_mc.k3.part.gz | `1aa39ef91961365dae253b34017e69598002a628219eac7220bd034005426b05` |
| cholesky_mc.k4.part.gz | `c55ddb1b77affe8bde9864bde9b0d7879276c8faf954b693ce8c85e6e954a9e0` |
| dart.k2.part.gz | `da7c4ec36b8a8798e432ffeecdef6160c44b4efdaded1507c93eae1ac2c56731` |
| dart.k3.part.gz | `51fd75127b44dffed27ac4bcbba199ad53cef6120a2e28d21cc3a6fa519f87fc` |
| dart.k4.part.gz | `c8c26c498a8a21b5d30fc1166237546ac717887741bd3c1d8db94a1dc0400329` |
| denoise.k2.part.gz | `8150e37951f578463d5940f1166c806962235249b4933c76b01f97905723b400` |
| denoise.k3.part.gz | `86d1b9c9acda4d9f5b3a4931acbfc14bf571340330f29305a83e2a2b313e0397` |
| denoise.k4.part.gz | `6fc33e07947779dfc384e0e5c4b633217126b74ad3e162fc052e1875bb4f27b7` |
| des90.k2.part.gz | `d080944518c2d65acc1da9baa2e29567085b0db308bf703d2c83ba9e3746a71e` |
| des90.k3.part.gz | `d01bb8badd34fb5bcbdfc5586d1c0aac722226c62cde6b6f62b241f318bcf586` |
| des90.k4.part.gz | `83cbcb5c5740386cfb5c94e7207c29b0b3fc14244b2147fd971b3d4657a41177` |
| directrf.k2.part.gz | `7cc6a7e0f43ac413c6535f23a5dd5d655fcdd510223a07f464575b27887b6f1f` |
| directrf.k3.part.gz | `2f49842efbb3ba46d8ced6534adece9a0fac4351d091cf69052ab66334b34981` |
| directrf.k4.part.gz | `b80234bd75298df04efb07f1b63df0301dd649ab1337f0611eb10172bf241793` |
| gsm_switch.k2.part.gz | `56d5ef210e4641e639df6441bd566769a91f858a09d897b5214ab73ba5fb588a` |
| gsm_switch.k3.part.gz | `b14e9d2ac4258762b68690f6b9e78d64e6af2fe7df252ea19fd12b382b887d8d` |
| gsm_switch.k4.part.gz | `01f334a4962acce8f3931c3b4546973ae6212bb9714d9280e55869bbea1fe82d` |
| mes_noc.k2.part.gz | `5a7ae0c6bb7009a7be227d183171d06d5371e8ab1e11d2350186b7b3f179e2e2` |
| mes_noc.k3.part.gz | `f811808b2c4cd8667cfef2e0bd4ccad16c282210c503c9d73cb317edaf0f9a4c` |
| mes_noc.k4.part.gz | `ed21d4bc612b617521308757c75c519ded422a169d14777730308c0f0ecef5cf` |
| minres.k2.part.gz | `c80d8b8a56b44765e91b580e532c792d97781c3f5e347b6645538c0742611ab0` |
| minres.k3.part.gz | `115fd615d4677936ce146b69cac83e9bb7972763c669af64a010f14b5bf470fb` |
| minres.k4.part.gz | `336d7b3ac300926774ee7190993deb467ee0de6d8002ee96dd45c53e54342ec1` |
| neuron.k2.part.gz | `4ad73ece425d802638daf2a36ce83b66a9df7b04efa620d88f1201196a3c54c5` |
| neuron.k3.part.gz | `2cbb19f47c49f44d31c2397c8749abf8eadddefe24bc24139f5b7e7e6d39a38a` |
| neuron.k4.part.gz | `44ca286e8de7a835e1fd772ee886cf89765c7df9d1ccb68b05d21d6dd8874e96` |
| openCV.k2.part.gz | `d62d0604efd86cdb5205dbc095a2f7f92b93cdd438352683fde964d18bb1d823` |
| openCV.k3.part.gz | `c8a255cf0a918a15ae24fddc7454604c4d7abc6e7502f2955801f3b6fcbd0770` |
| openCV.k4.part.gz | `844f63abfbeaca1d0eadf957f988263b923eaeed91265abe0f16704624de8d85` |
| segmentation.k2.part.gz | `54d3356c14422b628e6ecc26cb2d45a9fb5c4cf30a32c5431d84a318830f33fd` |
| segmentation.k3.part.gz | `238bf5bedce58c2c2fddbeeba0eaa3981a607f31492e81eae39609f04404dcc2` |
| segmentation.k4.part.gz | `91a4ae02ee8ea26f4268ca09dee1bfbbf431b05f2cc1b3cce036b7202dfa0481` |
| sparcT1_chip2.k2.part.gz | `7f4afeb0f4041a3ce200cf1fa6ae0a5bb15d8a61660e4a8000656641dd0737dd` |
| sparcT1_chip2.k3.part.gz | `053ad6e50101511fafe95a7ea451498c1f7c87a56963a21c494f191b9afbfe8b` |
| sparcT1_chip2.k4.part.gz | `2aad8641682239922cf4bc3a54cb27a3e0fc85f1464d05f02b358085e09be0f5` |
| sparcT1_core.k2.part.gz | `bb8e101577801a744bfb26974a9f65c056cd33986c99717eb9bba5a11f6744bd` |
| sparcT1_core.k3.part.gz | `7f1817c3f0e8f593aa88a5574eb16b9e64637d925a24736834c0d108f11a5054` |
| sparcT1_core.k4.part.gz | `8c2cabdcbacf3f44cc347fc70f845f196aa224454c2bbadad1c75c668d8e5035` |
| sparcT2_core.k2.part.gz | `29f5ce5958a0694784739409991c12ebd12f21d3c2e9eb60ff19eba29eff8ced` |
| sparcT2_core.k3.part.gz | `e5fbabbea738d9eb66887fea09c6377b67f46ea80a894143d75849639ec54cd3` |
| sparcT2_core.k4.part.gz | `88bd0b47b85e2afd522c0a1f24d0c5bf8319923c540e2e0129c37cfe0a7c4326` |
| stap_qrd.k2.part.gz | `29ba0008c95d1135ecc051b5d1473b68b192572eddc5bdd109a09f2c85ff25be` |
| stap_qrd.k3.part.gz | `7b4eda8d78a1ebc511379cb6df038a570d1472c597cb183010dff9b3c051e4e7` |
| stap_qrd.k4.part.gz | `80f3bc5a07db6483f6196f53d1d020bc3325ff99faf0442a3f43159d60356818` |
| stereo_vision.k2.part.gz | `a08baf4b42855d18a3550848bbde702960b0b3aa65feb9dd93308f672573aed0` |
| stereo_vision.k3.part.gz | `0761d799942f6094babff61f9301061b6cbc5747bc50100ddc5586c43a4ba4ee` |
| stereo_vision.k4.part.gz | `8a876700d06b9a1111a0233879b00d218258383cfef286b5015a25a9aa026d93` |

