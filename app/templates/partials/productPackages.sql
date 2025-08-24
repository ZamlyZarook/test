/*
 Navicat Premium Dump SQL

 Source Server         : IBIZ_ADMIN
 Source Server Type    : MySQL
 Source Server Version : 80039 (8.0.39)
 Source Host           : ibiz-erp-rds.cx680sm0mdjq.me-central-1.rds.amazonaws.com:3306
 Source Schema         : zalvo

 Target Server Type    : MySQL
 Target Server Version : 80039 (8.0.39)
 File Encoding         : 65001

 Date: 03/04/2025 14:53:35
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for productPackages
-- ----------------------------
DROP TABLE IF EXISTS `productPackages`;
CREATE TABLE `productPackages`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `product` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `value` double NULL DEFAULT NULL,
  `companyID` int NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 3 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of productPackages
-- ----------------------------
INSERT INTO `productPackages` VALUES (1, 'Gift', 50, 8);
INSERT INTO `productPackages` VALUES (2, 'Raffle', 25, 8);

SET FOREIGN_KEY_CHECKS = 1;
